"""推送系统 v2.0 — 竞价/信号/复盘 分阶段推送"""
import os, json, requests, logging, re
from datetime import datetime
from pathlib import Path
logger = logging.getLogger("aurora.push")

# ── 安全加固 S-1: 密钥只从 .env/环境变量读取 (禁止 config.yaml 明文) ──
_PROJ = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJ / ".env"
def _load_dotenv():
    """轻量 .env 读取 (有 python-dotenv 则优先, 否则手动解析 KEY=VALUE)."""
    if not _ENV_FILE.exists():
        return
    try:
        from dotenv import load_dotenv
    except Exception:
        load_dotenv = None
    if load_dotenv:
        load_dotenv(_ENV_FILE, override=False)
        return
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ and v:
            os.environ[k] = v

_load_dotenv()

def push_trade_execution(engine):
    """推送每笔交易执行详情 (买入/卖出)"""
    account = getattr(engine, "account", None)
    if not account:
        return
    trades = getattr(account, "trades", [])
    if not trades:
        return
    # 只推当日的交易
    today = datetime.now().strftime("%Y-%m-%d")
    today_trades = [t for t in trades if str(t.get("time", ""))[:10] == today]
    if not today_trades:
        return
    title = f"📊【工作流】交易执行 {datetime.now():%H:%M}"
    NL = chr(10)
    lines = []
    lines.append(f"【{today} 交易记录】")
    lines.append(f"市场: {getattr(engine,'market_regime','?')} ({getattr(engine,'market_score',0):.0f}/100)")
    buys = [t for t in today_trades if t.get("action") == "buy"]
    sells = [t for t in today_trades if t.get("action") == "sell"]
    if buys:
        lines.append(f"🟢 买入: {len(buys)}笔")
        for t in buys[-5:]:
            lines.append(f"  买入 {t.get('code','?')} {t.get('shares',0)}股 @{t.get('price',0):.2f}")
            lines.append(f"    ▸ {t.get('reason','')}")
    if sells:
        lines.append(f"🔴 卖出: {len(sells)}笔")
        for t in sells[-5:]:
            pnl = t.get("pnl", 0)
            pnl_s = f"盈亏{pnl:+.0f}" if pnl else ""
            lines.append(f"  卖出 {t.get('code','?')} {t.get('shares',0)}股 @{t.get('price',0):.2f} {pnl_s}")
            lines.append(f"    ▸ {t.get('reason','')}")
    info = account.get_account_info() if hasattr(account, "get_account_info") else {}
    lines.append(f"")
    lines.append(f"账户: 现金{info.get('cash',account.cash):,.0f} 总资产{info.get('total_value',account.total_value):,.0f}")
    # ⭐ 持仓明细（盈亏指导）
    positions = getattr(account, "positions", {}) or {}
    if positions:
        lines.append(f"持仓 {len(positions)}只:")
        for pc, pp in list(positions.items())[:6]:
            sh = pp.get("shares", 0)
            co = pp.get("avg_cost", 0)
            cu = pp.get("current_price", co) or co
            pnl_pct = (cu / co - 1) * 100 if co else 0
            pnl_amt = (cu - co) * sh if co else 0
            lines.append(f"  {pc} {sh}股 成本{co:.2f} 现价{cu:.2f} 盈亏{pnl_pct:+.1f}%({pnl_amt:+.0f})")
    else:
        lines.append("持仓: 0只")
    _send(title, NL.join(lines), engine)

def push_auction_results(engine):
    candidates = getattr(engine, "candidates", [])
    screened = getattr(engine, "screened", [])
    # 跳过空推送: 无候选且市场偏弱时无用
    if not candidates and not screened and engine.market_score < 50:
        logger.info("[Push] 竞价: 无候选,跳过")
        return
    title = f"🔍【工作流】竞价选股 {datetime.now():%m-%d %H:%M}"
    desc = f"市场: {engine.market_regime} ({engine.market_score:.0f}/100)\n候选: {len(candidates)}只\nCAN SLIM通过: {len(screened)}只\n"
    if screened:
        desc += "\nTOP 5:\n"
        for s in screened[:5]:
            desc += f"  {s.get('code','?')} {s.get('name','?')} CS={s.get('can_slim',0)}({s.get('cs_grade','?')})\n"
    _send(title, desc, engine)

def push_trade_signal(engine):
    plans = getattr(engine, "plans", [])
    alerts = getattr(engine, "alerts", [])
    t0 = getattr(engine, "t0_plans", [])
    if not plans and not alerts and not t0:
        logger.info("[Push] 信号: 无计划无告警,跳过")
        return
    title = f"📈【工作流】交易信号 {datetime.now():%H:%M}"
    desc = f"市场: {getattr(engine,'market_regime','?')} ({getattr(engine,'market_score',0):.0f}/100)\n"
    if plans:
        desc += f"🟢 开仓: {len(plans)}笔\n"
        for p in plans[:3]:
            desc += f"  {p.get('code','?')} {p.get('name','?')} {p.get('strategy','?')} @{p.get('entry_price',0):.2f} x{p.get('shares',0)} w={p.get('weight',0):.2f}\n"
    if t0:
        desc += f"\n🔄 T+0: {len(t0)}个\n"
        for t in t0[:3]:
            desc += f"  {t.get('code','?')} {t.get('t0_type','?')} {t.get('direction','?')} {t.get('shares',0)}sh score={t.get('score',0)}\n"
    if alerts:
        desc += f"\n⚠️ 告警: {len(alerts)}条\n"
        for a in alerts[:3]:
            desc += f"  [{a.get('type','?')}] {a.get('code','')} {a.get('msg','')}\n"
    _send(title, desc, engine)

def push_daily_review(engine):
    plans = getattr(engine, "plans", [])
    alerts = getattr(engine, "alerts", [])
    account = getattr(engine, "account", None)
    # 跳过空推送: 无交易无告警时无用
    if not plans and not alerts and engine.market_score < 50:
        logger.info("[Push] 复盘: 无交易,跳过")
        return
    title = f"📋【工作流】复盘 {datetime.now():%m-%d}"
    desc = f"市场: {engine.market_regime} ({engine.market_score:.0f}/100)\n今日交易: {len(plans)}笔\n告警: {len(alerts)}条\n"
    if account:
        info = account.get_account_info()
        desc += f"账户: 现金{info.get('cash',0):,.0f} 总{info.get('total_value',0):,.0f}\n持仓: {info.get('positions',0)}只\n"
    from strategies.evolution import get_all_health
    health = get_all_health()
    desc += "\n策略:\n"
    for n, h in list(health.items())[:5]:
        if h.get('trades', 0) > 0:
            desc += f"  {n}: {h['status']} wr={h.get('win_rate','?')}\n"
    from strategies.behavior import diagnose
    diag = diagnose()
    if diag.get("issues"):
        desc += f"\n⚠️ 行为: {'; '.join(diag['issues'])}"
    _send(title, desc, engine)

def push_morning_report(engine):
    # 跳过空晨报: 市场评分极低时数据不可靠
    if engine.market_score < 20:
        logger.info(f"[Push] 晨报: 市场{engine.market_score}<20,跳过")
        return
    candidates = getattr(engine, "candidates", [])
    screened = getattr(engine, "screened", [])
    title = "📰【工作流】晨报 " + datetime.now().strftime("%m-%d %H:%M")
    lines = []
    NL = chr(10)
    lines.append("【市场总览】")
    lines.append("大盘评分: " + str(engine.market_score) + "/100 | 状态: " + engine.market_regime)
    nb = getattr(engine, "northbound", {})
    lines.append("北向资金: " + str(nb.get("signal","N/A")))
    # 外围市场
    try:
        import urllib.request
        gcodes = {"hkHSI":"港股恒指","usDJI":"道琼斯","usIXIC":"纳指","usINX":"标普500"}
        gurl = "https://qt.gtimg.cn/q=" + ",".join(gcodes.keys())
        gdata = urllib.request.urlopen(gurl, timeout=8).read().decode("gbk", "replace")
        for gl in gdata.strip().split(";"):
            if not gl.strip() or "=" not in gl: continue
            gparts = gl.split('"')[1].split("~") if '"' in gl else []
            if len(gparts) >= 32:
                gk = gl.split("=")[0].split("_")[-1]
                gn = gcodes.get(gk, gparts[1])
                gp = gparts[3] if len(gparts)>3 else "?"
                gc = gparts[32] if len(gparts)>32 else "?"
                lines.append("  " + gn + ": " + gp + " (" + gc + "%)")
    except Exception:
        lines.append("  (外围数据获取失败)")
    lines.append("")
    lines.append("【板块热点TOP5】")
    try:
        from data.sources import get_sector_ranking
        sectors = (get_sector_ranking(10) or [])
        sectors.sort(key=lambda s: s.get("change_pct",0), reverse=True)
        for i, s in enumerate(sectors[:5]):
            lines.append(str(i+1) + ". " + str(s.get("name","")) + " " + "{:+.1f}%".format(s.get("change_pct",0)) + " 涨" + str(s.get("up",0)) + "跌" + str(s.get("down",0)))
    except Exception:
        lines.append("  (数据获取失败)")
    lines.append("")
    lines.append("【当前持仓】")
    pdir = Path(__file__).resolve().parent.parent
    sf = pdir / "data" / "sim_state.json"
    tf = pdir / "data" / "sim_trades.json"
    positions = {}
    trades = []
    if sf.exists():
        try:
            sd = json.loads(sf.read_text())
            positions = sd.get("positions", {})
        except: pass
    if tf.exists():
        try:
            trades = json.loads(tf.read_text())
        except: pass
    if positions:
        for code, pos in positions.items():
            sh = pos.get("shares",0)
            co = pos.get("avg_cost",0)
            cu = pos.get("current_price", co)
            pp = (cu/co-1)*100
            pnl = (cu-co)*sh
            lines.append(code + " " + str(sh) + "股 成本{:.2f} 现价{:.2f} 盈亏{:+.1f}%({:+.0f}元)".format(co,cu,pp,pnl))
            for t in reversed(trades):
                if t.get("action")=="buy" and t.get("code")==code:
                    lines.append("  买入: " + str(t.get("time",""))[:16])
                    break
    else:
        lines.append("  空仓")
    lines.append("")
    lines.append("【早盘选股】")
    if candidates:
        lines.append("候选股: " + str(len(candidates)) + "只 通过CAN SLIM: " + str(len(screened)) + "只")
        target = screened[:5] if screened else candidates[:5]
        for ci in target:
            g = str(ci.get("strong_grade","?"))
            sc = str(ci.get("strong_score", ci.get("can_slim",0)))
            lines.append("  " + str(ci.get("code","?")) + " " + str(ci.get("name","?")) + " " + g + "分=" + sc)
    else:
        lines.append("  今日无候选")
    lines.append("")
    lines.append("【今日策略】")
    ms = engine.market_score
    if ms < 25: lines.append("市场极弱, 全清仓观望")
    elif ms < 40: lines.append("市场偏弱, 持仓减半, 不开新仓")
    elif ms < 55: lines.append("震荡市, 持仓观察, 谨慎开仓")
    elif ms < 70: lines.append("市场偏强, 可半仓操作")
    else: lines.append("市场强势, 可满仓操作")
    if positions:
        for code, pos in positions.items():
            co = pos.get("avg_cost",0)
            cu = pos.get("current_price", co)
            pp = (cu/co-1)*100
            if pp >= 10: lines.append("  " + code + ": 盈利>10%, 建议减仓1/3锁利")
            elif pp >= 5: lines.append("  " + code + ": 盈利>5%, 设保本线至{:.2f}".format(co*1.05))
            elif pp >= 0: lines.append("  " + code + ": 微利持平, 持有观察")
            else: lines.append("  " + code + ": 亏损中, 关注止损位{:.2f}".format(co*0.95))
    tv = 0
    for p in positions.values():
        tv += p.get("shares",0) * p.get("current_price", p.get("avg_cost",0))
    ca = 0
    if sf.exists():
        try: ca = json.loads(sf.read_text()).get("cash",0)
        except: pass
    tv += ca
    lines.append("总资产: {:,}元 | 持仓: {}只 | 现金: {:,}元".format(int(tv), len(positions), int(ca)))
    _send(title, NL.join(lines), engine)


def push_trade_plan(engine):
    """推送当日交易计划"""
    plans = getattr(engine, "plans", [])
    scores = getattr(engine, "scores", [])
    analysis = getattr(engine, "analysis", [])
    if not plans and not scores:
        logger.info("[Push] 计划: 今日无交易计划")
        _send("📋【工作流】交易计划 " + datetime.now().strftime("%m-%d %H:%M"),
              "今日无符合条件的交易计划\n市场状态: " + str(engine.market_regime) + " (" + str(engine.market_score) + "/100)", engine)
        return
    title = "📋【工作流】交易计划 " + datetime.now().strftime("%m-%d %H:%M")
    NL = chr(10)
    lines = []
    lines.append("【市场状态】")
    lines.append(str(engine.market_regime) + " (" + str(engine.market_score) + "/100)")
    lines.append("")
    lines.append("【今日交易计划】")
    if plans:
        for p in plans[:5]:
            co = p.get("code","?")
            nm = p.get("name","?")
            st = p.get("strategy","?")
            ep = p.get("entry_price",0)
            sh = p.get("shares",0)
            sl = p.get("stop_loss",0)
            tp = p.get("take_profit",0)
            wg = p.get("weight",0)
            lines.append(str(co) + " " + str(nm))
            lines.append("  策略:" + str(st) + " 价格:" + "{:.2f}".format(ep) + " 股数:" + str(sh))
            lines.append("  止损:" + "{:.2f}".format(sl) + " 止盈:" + "{:.2f}".format(tp) + " 仓位:" + "{:.0%}".format(wg))
            lines.append("")
    else:
        lines.append("  今日无计划开仓")
    lines.append("")
    lines.append("【评分前列(待观察)】")
    if scores:
        for s in scores[:3]:
            lines.append("  " + str(s.get("code","?")) + " 综合评分:" + str(s.get("composite",0)) + " 策略:" + str(s.get("best_strategy","?")))
    lines.append("")
    lines.append("总策略: " + str(len(analysis)) + "只 | 计划开仓: " + str(len(plans)) + "只")
    # v14.46: body_only=True — 交易计划同一天只推一次(配合engine_live session节流)
    _send(title, NL.join(lines), engine, body_only=True)


_CSUFFIX = "\n\n⚠️ 基于公开数据的历史回测分析，仅供参考，不构成投资建议。"
_REDLIST = [
    (r"(建议|关注|提醒)", "分析提示"),
    (r"(目标价|涨到|跌到|预计)\s*\d+", "【保留判断】"),
    (r"(预期|预计|预测)(收益|回报)\s*\d*%?", "历史回测表明"),
]
def _comply(text):
    for pat, repl in _REDLIST:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    return text + _CSUFFIX if len(text) > 60 else text

def _send(title, desc, engine, body_only: bool = False):
    title = _comply(title)
    desc = _comply(desc)
    # 安全加固 S-1: token 只从环境变量 SCT_TOKEN 读取 (config.yaml 不再存明文)。
    # 无 token 时降级为「跳过推送 + 日志警告」, 绝不伪造/重放旧凭据。
    token = os.environ.get("SCT_TOKEN", "").strip()
    if not token or len(token) < 10:
        logger.warning("[Push] 未配置有效的 SCT_TOKEN (请设置环境变量/.env), 跳过推送: %s", title[:30])
        return
    try:
        # ⭐ 2026-08-10: 同一条内容只推一次（24h 窗口去重）
        # v14.46: body_only=True 时仅标题指纹(交易计划专用) — desc含不同股票代码,
        #         用desc指纹永不撞→刷屏; 仅标题指纹使"今日交易计划"同一天只推一次
        from notify.dedup import should_push
        if not should_push("push", title, desc, body_only=body_only):
            logger.info(f"[Push] 去重跳过(24h内已推): {title[:30]}...")
            return
        requests.post(f"https://sctapi.ftqq.com/{token}.send",
            json={"title": title, "desp": desc}, timeout=10)
        logger.info(f"[Push] {title[:30]}...")
    except Exception as e:
        logger.warning("[Push] 发送失败: %s", e)