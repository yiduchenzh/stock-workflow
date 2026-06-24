"""推送系统 v2.0 — 竞价/信号/复盘 分阶段推送"""
import os, json, requests, logging
from datetime import datetime
from pathlib import Path
logger = logging.getLogger("aurora.push")

def push_auction_results(engine):
    candidates = getattr(engine, "candidates", [])
    screened = getattr(engine, "screened", [])
    # 跳过空推送: 无候选且市场偏弱时无用
    if not candidates and not screened and engine.market_score < 50:
        logger.info("[Push] 竞价: 无候选,跳过")
        return
    title = f"🔍 Aurora 竞价选股 {datetime.now():%m-%d %H:%M}"
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
    title = f"📈 Aurora 交易信号 {datetime.now():%H:%M}"
    desc = ""
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
    title = f"📋 Aurora 复盘 {datetime.now():%m-%d}"
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
    title = "Aurora晨报 " + datetime.now().strftime("%m-%d %H:%M")
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


def _send(title, desc, engine):
    token = engine.cfg.get("notify", {}).get("sct_token", "")
    if not token: return
    try:
        token = os.environ.get("SCT_TOKEN", token)
        if not token or len(token) < 10: return
        requests.post(f"https://sctapi.ftqq.com/{token}.send",
            json={"title": title, "desp": desc}, timeout=10)
        logger.info(f"[Push] {title[:30]}...")
    except Exception: pass