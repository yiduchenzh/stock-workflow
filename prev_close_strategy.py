# -*- coding: utf-8 -*-
"""
昨收价极简交易体系 — 数据获取 + 信号生成 + 回测（单文件自包含）

▌战法来源
  实盘提炼的极简体系：删掉 80% 指标，只盯"昨日收盘价"一个数字。
  - 昨收价 = 前一日全市场资金博弈的真实共识（无法造假、零滞后）
  - 站上昨收 = 多头优势；跌破昨收 = 空头占优
  - 所有盘中涨跌、真假突破、诱多诱空，全部围绕昨收价展开

▌蒸馏后的可编码规则

  买点A（挖坑转强 / 弱势转强势）：
    当日 open  < prev_close   （低开/平开后下杀）
    当日 low   < prev_close   （盘中跌破昨收 = 挖坑）
    当日 close > prev_close   （收盘收回站稳 = 洗盘结束）
    → 次日开盘买入

  买点B（强势延续 / 回踩不破）：
    当日 open  >= prev_close  （站稳开盘）
    当日 low   >= prev_close  （回踩不破昨收）
    当日 close >  prev_close  （收阳确认）
    且当日涨幅 < 9%（涨停无法买入，防追高）
    → 次日开盘买入

  离场（核心铁律，二选一）：
    ① 破位离场：持有中任一日 close < prev_close → 次日开盘卖出
       （"跌破昨收无法收回立刻离场"，随价格上移天然形成移动止盈）
    ② 硬止损：收盘价 < 买入价 × 0.92 → 次日开盘卖出（极端保护）

  持仓上限：60 个交易日（让利润奔跑，但防长期僵持）

▌防骗线处理（日线级近似）
  原文要求"15分钟有效站稳才算有效突破"——日线回测用
  "收盘确认"（close vs prev_close）等价替代，天然过滤盘中瞬时穿越。

▌用法
  python prev_close_strategy.py --codes 600519,000858,601318 --years 2
  python prev_close_strategy.py --codes 600519 --years 3 --capital 200000
"""
import sys, json, time, argparse
import urllib.request
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


# ══════════════════════════════════════════════════════════════
# 1. 数据获取（腾讯日K，自包含，无外部依赖）
# ══════════════════════════════════════════════════════════════

def _prefix(code: str) -> str:
    """6位代码 → 腾讯前缀 (92/8/4开头=北交所bj, 6/9=sh, 其余=sz)"""
    if code.startswith(("92", "8", "4")):
        return f"bj{code}"
    return f"sh{code}" if code.startswith(("6", "9")) else f"sz{code}"


def fetch_kline(code: str, days: int = 500, tf: str = "day") -> pd.DataFrame:
    """腾讯K线: tf=day日线(前复权) / m5/m15/m30/m60分钟(不复权)
    返回 {date, open, close, high, low, volume}
    """
    pfx = _prefix(code)
    if tf == "day":
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={pfx},day,,,{days},qfq"
        key = "qfqday"
    else:
        # 分钟K线: 约8天=2000根15分钟, days参数按根数
        url = f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={pfx},{tf},,,{days},"
        key = tf
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    node = data.get("data", {}).get(pfx, {})
    rows = node.get(key, []) or node.get("day", [])
    if not rows:
        return pd.DataFrame()
    # 行结构: [时间,开,收,高,低,量, ...]; 分钟行可能含除权dict等, 只取前6列
    rows = [row[:6] for row in rows]
    df = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "volume"])
    for col in ("open", "close", "high", "low", "volume"):
        df[col] = df[col].astype(float)
    df["date"] = pd.to_datetime(df["date"],
                                format="%Y%m%d%H%M" if tf != "day" else None)
    return df


# ══════════════════════════════════════════════════════════════
# 2. 信号生成（昨收价四态 + 两类买点）
# ══════════════════════════════════════════════════════════════

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """基于昨收价生成信号:
    返回 df 附加列:
      prev_close  昨收价
      pattern     当日形态: strong_bull(站稳回踩不破) / weak_bear(压制) /
                   oscillation(反复穿越) / fake(骗线)
      signal_A    挖坑转强买点(次日买入)
      signal_B    强势延续买点(次日买入)
    """
    d = df.copy()
    d["prev_close"] = d["close"].shift(1)
    d = d.dropna(subset=["prev_close"]).reset_index(drop=True)

    # ── 四种盘口形态识别 ──
    opened_above = d["open"] >= d["prev_close"]      # 站稳昨收开盘
    low_held = d["low"] >= d["prev_close"]           # 回踩不破
    closed_above = d["close"] > d["prev_close"]      # 收在昨收上方
    closed_below = d["close"] < d["prev_close"]      # 收在昨收下方
    touched = (d["low"] < d["prev_close"]) & (d["prev_close"] <= d["high"])  # 盘中穿越昨收

    pattern = np.full(len(d), "oscillation", dtype=object)
    pattern[opened_above & low_held & closed_above] = "strong_bull"   # 形态1: 站稳+回踩不破
    pattern[~opened_above & ~closed_above] = "weak_bear"              # 形态2: 压制昨收下方
    pattern[opened_above & touched & ~closed_above] = "fake"          # 形态4: 假突破(盘中穿越但收跌)
    d["pattern"] = pattern

    # ── 买点A: 挖坑转强 (低开+盘中破位+收盘收回) ──
    buy_A = (d["open"] < d["prev_close"]) & (d["low"] < d["prev_close"]) & closed_above
    # ── 买点B: 强势延续 (站稳+回踩不破+收阳), 且非涨停(涨幅<9%可买入) ──
    chg = d["close"] / d["prev_close"] - 1
    buy_B = opened_above & low_held & closed_above & (chg < 0.09)
    # 涨停一字板(open=close=high且涨幅≥9.5%)排除
    limit_up = (chg >= 0.095) & (d["open"] == d["close"])
    buy_B = buy_B & ~limit_up

    d["signal_A"] = buy_A
    d["signal_B"] = buy_B
    d["signal"] = buy_A | buy_B
    return d


# ══════════════════════════════════════════════════════════════
# 3. 回测引擎（信号次日开盘买入 → 破昨收离场）
# ══════════════════════════════════════════════════════════════

def backtest_single(df: pd.DataFrame, capital: float = 100_000,
                    max_hold: int = 60, stop_pct: float = 0.08,
                    entry_mode: str = "next_open") -> dict:
    """单标的回测
    entry_mode:
      next_open  — 信号次日开盘买入(保守, 防未来函数)
      same_close — 信号当日收盘价买入(忠实原文"回踩昨收低吸"的日内操作)
    同一时间只持有一个仓位(有持仓时新信号忽略)
    """
    trades = []
    equity_curve = []   # (date, equity)
    cash = capital
    pos = None          # {entry_date, entry_price, shares, signal_type, pattern}

    opens = df["open"].values
    closes = df["close"].values
    dates = df["date"].values
    prevs = df["prev_close"].values
    sigs = df["signal"].values

    for i in range(len(df)):
        date, open_px, close_px, prev = dates[i], opens[i], closes[i], prevs[i]

        # ── ① 先执行"昨日收盘触发的离场"（今日开盘价卖出，无未来函数）──
        if pos is not None and pos.get("pending_exit"):
            reason = pos.pop("pending_exit")
            sell_px = open_px
            proceeds = sell_px * pos["shares"]
            pnl = proceeds - pos["cost"]
            pnl_pct = pnl / pos["cost"] * 100
            trades.append({
                "code": df.attrs.get("code", "?"),
                "entry_date": str(pos["entry_date"])[:10],
                "entry_price": round(pos["entry_price"], 3),
                "exit_date": str(pd.Timestamp(date))[:10],
                "exit_price": round(sell_px, 3),
                "hold_days": i - pos["entry_idx"],
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "signal": pos["signal"],
                "pattern": pos["pattern"],
                "exit_reason": reason,
            })
            cash += proceeds  # 累加(保留买入后剩余现金, 不覆盖)
            pos = None

        # ── ② 收盘判断: 是否触发离场（标记, 次日开盘执行）──
        if pos is not None and not pos.get("pending_exit"):
            # ① 破位离场: 今日收盘 < 昨收（核心铁律）
            if close_px < prev:
                pos["pending_exit"] = "break_prev_close"
            # ② 硬止损: 收盘 < 买入价×(1-stop)
            elif close_px < pos["entry_price"] * (1 - stop_pct):
                pos["pending_exit"] = "hard_stop"
            # ③ 超期: 持仓超过 max_hold 天
            elif (i - pos["entry_idx"]) >= max_hold:
                pos["pending_exit"] = "max_hold"

        # ── ③ 开仓判断 ──
        #  next_open: 昨日信号 → 今日开盘买入
        #  same_close: 今日信号 → 今日收盘价买入(忠实原文日内低吸)
        want_buy = False
        if pos is None:
            if entry_mode == "same_close" and sigs[i]:
                want_buy = True
                buy_px = close_px  # 信号当日收盘价(近似日内低吸成交)
            elif entry_mode == "next_open" and i > 0 and sigs[i - 1]:
                want_buy = True
                buy_px = open_px
        if want_buy:
            if buy_px <= 0:
                continue
            shares = int(cash * 0.98 / buy_px / 100) * 100  # 全仓(留2%费用)
            if shares < 100:
                continue
            sig_i = i if entry_mode == "same_close" else i - 1
            pos = {
                "entry_date": pd.Timestamp(date), "entry_price": buy_px,
                "shares": shares, "cost": buy_px * shares,
                "entry_idx": i,
                "signal": "A" if df["signal_A"].iloc[sig_i] else "B",
                "pattern": df["pattern"].iloc[sig_i],
            }
            cash -= buy_px * shares  # 只扣实际买入花费(剩余现金保留)

        # ── 每日权益记录: 现金 + 持仓市值(单口径, 不重复计算) ──
        cur_equity = cash + (pos["shares"] * close_px if pos else 0)
        equity_curve.append((pd.Timestamp(date), round(cur_equity, 2)))

    # 期末强制平仓
    if pos is not None:
        last_px = closes[-1]
        proceeds = last_px * pos["shares"]
        pnl = proceeds - pos["cost"]
        trades.append({
            "code": df.attrs.get("code", "?"),
            "entry_date": str(pos["entry_date"])[:10],
            "entry_price": round(pos["entry_price"], 3),
            "exit_date": str(pd.Timestamp(dates[-1]))[:10],
            "exit_price": round(last_px, 3),
            "hold_days": len(df) - 1 - pos["entry_idx"],
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / pos["cost"] * 100, 2),
            "signal": pos["signal"],
            "pattern": pos["pattern"],
            "exit_reason": "period_end",
        })
        cash += proceeds  # 累加(期末平仓同理)

    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "final_equity": round(cash, 2),
        "capital": capital,
    }


# ══════════════════════════════════════════════════════════════
# 3.5 分钟级忠实回测 (完整还原原文规则)
# ══════════════════════════════════════════════════════════════

def backtest_minute(df: pd.DataFrame, capital: float = 100_000,
                    bars_per_day: int = 16, stop_pct: float = 0.05) -> dict:
    """分钟级回测 — 忠实还原昨收价体系原文规则:
    - 昨收价 = 每个交易日的分界线(前一日最后一根bar收盘)
    - 买点A(挖坑转强): 盘中跌破昨收, 10分钟内收回站稳昨收上方 → 低吸
    - 买点B(强势延续): 开盘站稳昨收, 回踩不破, 缩量企稳后放量 → 加仓
    - 离场: 放量有效跌破昨收且15分钟无法收回 → 卖出
    - 防骗线: 短暂穿越(<15分钟)不做决策
    bars_per_day: 16=15分钟bar(4小时交易), 48=5分钟bar
    """
    trades = []
    equity_curve = []
    cash = capital
    pos = None
    dates = df["date"].values
    opens = df["open"].values
    closes = df["close"].values
    lows = df["low"].values
    highs = df["high"].values
    vols = df["volume"].values
    n = len(df)

    # 每个交易日首bar索引(用于取昨收)
    day_idx = []
    cur_day = None
    for i in range(n):
        d = pd.Timestamp(dates[i]).date()
        if d != cur_day:
            cur_day = d
            day_idx.append(i)

    # 构建 bar -> 昨收映射 (该日首bar之前一日收盘)
    prev_close_map = {}
    for j, idx in enumerate(day_idx):
        if j > 0:
            pc = closes[idx - 1]  # 前一日最后一bar收盘 = 昨收
            for i in range(idx, day_idx[j + 1] if j + 1 < len(day_idx) else n):
                prev_close_map[i] = pc
        else:
            for i in range(idx, day_idx[j + 1] if j + 1 < len(day_idx) else n):
                prev_close_map[i] = None  # 首日无昨收

    pending_buy = None   # 买点触发, 待下一bar确认
    break_start = -1     # 跌破昨收起始bar(用于15分钟判定)
    breach_dur = 0       # 持续破位bar数

    for i in range(n):
        pc = prev_close_map.get(i)
        if pc is None:
            equity_curve.append((pd.Timestamp(dates[i]), round(cash, 2)))
            continue
        d = pd.Timestamp(dates[i])
        o, c, l, h, v = opens[i], closes[i], lows[i], highs[i], vols[i]

        # ── 持仓中的离场判断: 放量有效跌破昨收+15分钟不收回 ──
        if pos is not None:
            if c < pc:
                breach_dur += 1
            else:
                breach_dur = 0
            if breach_dur >= 2:  # 2根15分钟≈30分钟持续在昨收下(原文"15分钟无法收回"保守近似)
                # 且非缩量(放量破位确认)
                if v >= pos.get("avg_vol", 1):
                    proceeds = o * pos["shares"]
                    pnl = proceeds - pos["cost"]
                    pnl_pct = pnl / pos["cost"] * 100
                    trades.append({
                        "code": df.attrs.get("code", "?"),
                        "entry_date": str(pos["entry_date"])[:16],
                        "entry_price": round(pos["entry_price"], 3),
                        "exit_date": str(d)[:16],
                        "exit_price": round(o, 3),
                        "hold_bars": i - pos["entry_idx"],
                        "pnl": round(pnl, 2),
                        "pnl_pct": round(pnl_pct, 2),
                        "signal": pos["signal"],
                        "exit_reason": "break_prev_close",
                    })
                    cash += proceeds
                    pos = None
                    breach_dur = 0
                    continue
            # 硬止损
            if pos is not None and c < pos["entry_price"] * (1 - stop_pct):
                proceeds = o * pos["shares"]
                pnl = proceeds - pos["cost"]
                trades.append({
                    "code": df.attrs.get("code", "?"),
                    "entry_date": str(pos["entry_date"])[:16],
                    "entry_price": round(pos["entry_price"], 3),
                    "exit_date": str(d)[:16],
                    "exit_price": round(o, 3),
                    "hold_bars": i - pos["entry_idx"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl / pos["cost"] * 100, 2),
                    "signal": pos["signal"],
                    "exit_reason": "hard_stop",
                })
                cash += proceeds
                pos = None
                breach_dur = 0
                continue

        # ── 买点A: 挖坑转强 (跌破昨收 → 10分钟内收回站稳) ──
        if pos is None:
            if pending_buy:
                # 已触发买点A, 检查收回确认(当前bar站回昨收上方)
                if c > pc:
                    buy_px = c  # 收回瞬间价(近似)
                    shares = int(cash * 0.98 / buy_px / 100) * 100
                    if shares >= 100:
                        pos = {
                            "entry_date": d, "entry_price": buy_px, "shares": shares,
                            "cost": buy_px * shares, "entry_idx": i, "signal": "A",
                            "avg_vol": np.mean(vols[max(0, i - bars_per_day * 5):i]),
                        }
                        cash -= buy_px * shares
                    pending_buy = None
                elif i - pending_buy > bars_per_day:  # 超过1天未收回, 放弃
                    pending_buy = None
            elif l < pc:  # 盘中跌破昨收 → 触发买点A观察
                pending_buy = i
            elif o >= pc and h > pc and c > pc:  # 买点B: 站稳开盘+收阳
                if v >= 1.2 * np.mean(vols[max(0, i - bars_per_day * 5):i]) if i > bars_per_day else True:
                    buy_px = c
                    shares = int(cash * 0.98 / buy_px / 100) * 100
                    if shares >= 100:
                        pos = {
                            "entry_date": d, "entry_price": buy_px, "shares": shares,
                            "cost": buy_px * shares, "entry_idx": i, "signal": "B",
                            "avg_vol": np.mean(vols[max(0, i - bars_per_day * 5):i]),
                        }
                        cash -= buy_px * shares

        cur_equity = cash + (pos["shares"] * c if pos else 0)
        equity_curve.append((pd.Timestamp(dates[i]), round(cur_equity, 2)))

    # 期末平仓
    if pos is not None:
        proceeds = closes[-1] * pos["shares"]
        pnl = proceeds - pos["cost"]
        trades.append({
            "code": df.attrs.get("code", "?"),
            "entry_date": str(pos["entry_date"])[:16],
            "entry_price": round(pos["entry_price"], 3),
            "exit_date": str(pd.Timestamp(dates[-1]))[:16],
            "exit_price": round(closes[-1], 3),
            "hold_bars": n - 1 - pos["entry_idx"],
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / pos["cost"] * 100, 2),
            "signal": pos["signal"],
            "exit_reason": "period_end",
        })
        cash += proceeds

    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "final_equity": round(cash, 2),
        "capital": capital,
    }


# ══════════════════════════════════════════════════════════════
# 3.6 多周期共振回测 (完整复原原文三层架构)
#  ══════════════════════════════════════════════════════════════

def _classify_position(daily: pd.DataFrame) -> dict:
    """日线位置判断: 基于近60日高低点分位
    low<20% → 低位(洗盘概率大), 20-80% → 中位, >80% → 高位(出货风险)
    返回 {date: 'low'/'mid'/'high'}
    """
    pos = {}
    closes = daily["close"].values
    dates = daily["date"].values
    lookback = 60
    for i in range(len(daily)):
        lo = i - lookback + 1
        if lo < 0:
            lo = 0
        seg = closes[lo:i + 1]
        if len(seg) < 30:
            pos[pd.Timestamp(dates[i]).date()] = "mid"
            continue
        pct = (closes[i] - seg.min()) / (seg.max() - seg.min()) if seg.max() > seg.min() else 0.5
        pos[pd.Timestamp(dates[i]).date()] = (
            "low" if pct < 0.2 else ("high" if pct > 0.8 else "mid"))
    return pos


def _opening_bias(df_m1: pd.DataFrame) -> dict:
    """开盘3分钟定强弱 (9:30-9:33, 3根1分钟bar):
    strong: 3分钟站稳昨收(高开+不回落) → 真强势, 备选低吸
    weak:   3分钟压制昨收(低开+反弹无力) → 真弱势, 全天规避
    oscillation: 反复穿越 → 观望
    返回 {date: 'strong'/'weak'/'oscillation'}
    """
    bias = {}
    dates = df_m1["date"].values
    opens = df_m1["open"].values
    closes = df_m1["close"].values
    # 按日分组
    day_groups = {}
    for i in range(len(df_m1)):
        d = pd.Timestamp(dates[i])
        day_groups.setdefault(d.date(), []).append(i)
    for day, idxs in day_groups.items():
        if len(idxs) < 3:
            continue
        # 昨收 = 前一日最后一根bar收盘(用前一日数据)
        prev_day = None
        for pd_ in sorted(day_groups.keys()):
            if pd_ < day:
                prev_day = pd_
        if prev_day is None:
            bias[day] = "oscillation"
            continue
        pc = closes[day_groups[prev_day][-1]]
        # 开盘3根bar: 9:30/9:31/9:32 (1分钟)
        first3 = idxs[:3]
        o1 = opens[first3[0]]
        c3 = closes[first3[-1]]
        if o1 >= pc and c3 > pc:
            bias[day] = "strong"
        elif o1 < pc and c3 < pc:
            bias[day] = "weak"
        else:
            bias[day] = "oscillation"
    return bias


def _opening_bias_m15(df_m15: pd.DataFrame) -> dict:
    """开盘基调降级版: 用m15第1根bar(9:30-9:45)判断当日强弱
    当m1数据不足时替代 _opening_bias (15分钟站稳≈开盘3分钟的保守近似)
    """
    bias = {}
    dates = df_m15["date"].values
    opens = df_m15["open"].values
    closes = df_m15["close"].values
    day_groups = {}
    for i in range(len(df_m15)):
        d = pd.Timestamp(dates[i])
        day_groups.setdefault(d.date(), []).append(i)
    for day, idxs in day_groups.items():
        if not idxs:
            continue
        prev_day = None
        for pd_ in sorted(day_groups.keys()):
            if pd_ < day:
                prev_day = pd_
        if prev_day is None:
            bias[day] = "oscillation"
            continue
        pc = closes[day_groups[prev_day][-1]]
        # 首根15分钟bar: 9:30-9:45
        i0 = idxs[0]
        o1 = opens[i0]
        c1 = closes[i0]
        if o1 >= pc and c1 > pc:
            bias[day] = "strong"
        elif o1 < pc and c1 < pc:
            bias[day] = "weak"
        else:
            bias[day] = "oscillation"
    return bias


def backtest_multitf(df_m1: pd.DataFrame, df_m15: pd.DataFrame,
                     daily: pd.DataFrame, capital: float = 100_000,
                     stop_pct: float = 0.05, require_sector: bool = False,
                     sector_map: dict = None) -> dict:
    """多周期共振回测 — 完整复原昨收价体系:
    ① 日线: 昨收分界线 + 位置(低位/中位/高位) + 板块联动
    ② 开盘3分钟(m1): 定当日强弱基调
    ③ 15分钟: 执行买卖点(买点A挖坑转强/买点B强势延续/破位离场)
    共振规则:
      - 高位股票: 只允许买点A(挖坑转强), 买点B禁止(防高位假突破)
      - 开盘弱势: 禁止买点B(强势延续), 只允许买点A(挖坑转强低吸)
      - 开盘强势/震荡: 两买点均可
      - 板块联动(require_sector=True): 个股板块涨幅>0才做多
    """
    trades = []
    equity_curve = []
    cash = capital
    pos = None

    dates = df_m15["date"].values
    opens = df_m15["open"].values
    closes = df_m15["close"].values
    lows = df_m15["low"].values
    highs = df_m15["high"].values
    vols = df_m15["volume"].values
    n = len(df_m15)

    # 构建 m15 bar -> 昨收 + 当日基调
    day_idx = []
    cur_day = None
    for i in range(n):
        d = pd.Timestamp(dates[i]).date()
        if d != cur_day:
            cur_day = d
            day_idx.append(i)

    # 日线位置映射 {date: low/mid/high}
    positions = _classify_position(daily)
    # 开盘3分钟强弱 {date: strong/weak/oscillation}
    # 优先m1(精确3分钟), m1覆盖不足时用m15首根bar降级
    opening = _opening_bias(df_m1) if len(df_m1) >= 200 else {}
    if len(opening) < len(day_idx) // 2:
        m15_bias = _opening_bias_m15(df_m15)
        m15_bias.update({k: v for k, v in opening.items() if k in m15_bias})
        opening = m15_bias

    info = {}  # i -> {pc, pos, bias}
    for j, idx in enumerate(day_idx):
        if j > 0:
            pc = closes[idx - 1]
        else:
            pc = None
        end = day_idx[j + 1] if j + 1 < len(day_idx) else n
        d0 = pd.Timestamp(dates[idx]).date()
        for i in range(idx, end):
            info[i] = {
                "pc": pc,
                "pos": positions.get(d0, "mid"),
                "bias": opening.get(d0, "oscillation"),
            }

    pending_buy = None
    breach_dur = 0

    for i in range(n):
        inf = info.get(i)
        if inf is None or inf["pc"] is None:
            equity_curve.append((pd.Timestamp(dates[i]), round(cash, 2)))
            continue
        pc = inf["pc"]
        d = pd.Timestamp(dates[i])
        o, c, l, h, v = opens[i], closes[i], lows[i], highs[i], vols[i]
        pos_lvl = inf["pos"]
        bias = inf["bias"]

        # ── 板块联动过滤(可选): 板块涨幅>0才允许持仓 ──
        if require_sector and sector_map is not None:
            sector_ok = sector_map.get(d.date(), 0) > 0
        else:
            sector_ok = True

        # ── 离场: 放量有效跌破昨收+15分钟不收回 ──
        if pos is not None:
            if c < pc:
                breach_dur += 1
            else:
                breach_dur = 0
            if breach_dur >= 2 and v >= pos.get("avg_vol", 1):
                proceeds = o * pos["shares"]
                pnl = proceeds - pos["cost"]
                trades.append({
                    "code": df_m15.attrs.get("code", "?"),
                    "entry_date": str(pos["entry_date"])[:16],
                    "entry_price": round(pos["entry_price"], 3),
                    "exit_date": str(d)[:16],
                    "exit_price": round(o, 3),
                    "hold_bars": i - pos["entry_idx"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl / pos["cost"] * 100, 2),
                    "signal": pos["signal"],
                    "exit_reason": "break_prev_close",
                    "pos_level": pos_lvl, "bias": bias,
                })
                cash += proceeds
                pos = None
                breach_dur = 0
                continue
            if c < pos["entry_price"] * (1 - stop_pct):
                proceeds = o * pos["shares"]
                pnl = proceeds - pos["cost"]
                trades.append({
                    "code": df_m15.attrs.get("code", "?"),
                    "entry_date": str(pos["entry_date"])[:16],
                    "entry_price": round(pos["entry_price"], 3),
                    "exit_date": str(d)[:16],
                    "exit_price": round(o, 3),
                    "hold_bars": i - pos["entry_idx"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl / pos["cost"] * 100, 2),
                    "signal": pos["signal"],
                    "exit_reason": "hard_stop",
                    "pos_level": pos_lvl, "bias": bias,
                })
                cash += proceeds
                pos = None
                breach_dur = 0
                continue

        # ── 买点A: 挖坑转强(跌破昨收→收回) — 所有位置/基调均允许 ──
        if pos is None and sector_ok:
            if pending_buy:
                if c > pc:
                    buy_px = c
                    shares = int(cash * 0.98 / buy_px / 100) * 100
                    if shares >= 100:
                        pos = {
                            "entry_date": d, "entry_price": buy_px, "shares": shares,
                            "cost": buy_px * shares, "entry_idx": i, "signal": "A",
                            "avg_vol": np.mean(vols[max(0, i - 80):i]),
                        }
                        cash -= buy_px * shares
                    pending_buy = None
                elif i - pending_buy > 16:
                    pending_buy = None
            elif l < pc:
                pending_buy = i
            # ── 买点B: 强势延续 — 需开盘非弱势 + 非高位 ──
            elif o >= pc and h > pc and c > pc and bias != "weak" and pos_lvl != "high":
                avg_v = np.mean(vols[max(0, i - 80):i]) if i > 80 else v
                if avg_v > 0 and v >= 1.2 * avg_v:  # 放量确认
                    buy_px = c
                    shares = int(cash * 0.98 / buy_px / 100) * 100
                    if shares >= 100:
                        pos = {
                            "entry_date": d, "entry_price": buy_px, "shares": shares,
                            "cost": buy_px * shares, "entry_idx": i, "signal": "B",
                            "avg_vol": avg_v,
                        }
                        cash -= buy_px * shares

        cur_equity = cash + (pos["shares"] * c if pos else 0)
        equity_curve.append((pd.Timestamp(dates[i]), round(cur_equity, 2)))

    if pos is not None:
        proceeds = closes[-1] * pos["shares"]
        pnl = proceeds - pos["cost"]
        trades.append({
            "code": df_m15.attrs.get("code", "?"),
            "entry_date": str(pos["entry_date"])[:16],
            "entry_price": round(pos["entry_price"], 3),
            "exit_date": str(pd.Timestamp(dates[-1]))[:16],
            "exit_price": round(closes[-1], 3),
            "hold_bars": n - 1 - pos["entry_idx"],
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / pos["cost"] * 100, 2),
            "signal": pos["signal"],
            "exit_reason": "period_end",
            "pos_level": "?", "bias": "?",
        })
        cash += proceeds

    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "final_equity": round(cash, 2),
        "capital": capital,
    }


# ══════════════════════════════════════════════════════════════
# 3.7 组合回测 (多标的共享资金池)
# ══════════════════════════════════════════════════════════════

def backtest_portfolio(sig_dfs: dict, capital: float = 1_000_000,
                       max_positions: int = 3, stop_pct: float = 0.08,
                       entry_mode: str = "next_open") -> dict:
    """多标的组合回测 — 共享资金池, 等权分配:
    - 每只股票独立生成信号(昨收价体系), 但共用同一资金池
    - 最多同时持仓 max_positions 只, 每只目标仓位 = 资金/max_positions
    - 信号触发时: 若持仓未满且现金足够 → 买入; 满仓则跳过(等腾出位置)
    - 离场: 各标的独立(跌破昨收/硬止损/超期)
    sig_dfs: {code: 已加信号列的DataFrame}
    """
    trades = []
    # 按日期推进: 合并所有标的的交易日历
    all_dates = sorted(set().union(*[set(df["date"].values) for df in sig_dfs.values()]))
    # 构建每个标的 {date_idx -> 当日bar信息}
    data = {}
    for code, df in sig_dfs.items():
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "date": r["date"], "open": r["open"], "close": r["close"],
                "signal": bool(r["signal"]), "signal_A": bool(r["signal_A"]),
                "signal_B": bool(r["signal_B"]), "prev_close": r["prev_close"],
            })
        data[code] = {str(pd.Timestamp(r["date"]).date()): r for r in rows}

    cash = capital
    positions = {}   # code -> {entry_date, entry_price, shares, cost, entry_idx, pending_exit}
    equity_curve = []
    date_list = [str(pd.Timestamp(d).date()) for d in all_dates]

    # 等权目标仓位
    target_value = capital / max_positions

    for di, ds in enumerate(date_list):
        # ── ① 先执行离场(各标的独立) ──
        for code in list(positions.keys()):
            pos = positions[code]
            bar = data[code].get(ds)
            if bar is None:
                continue
            if pos.get("pending_exit"):
                # 今日开盘卖出
                sell_px = bar["open"]
                proceeds = sell_px * pos["shares"]
                pnl = proceeds - pos["cost"]
                trades.append({
                    "code": code,
                    "entry_date": str(pos["entry_date"])[:10],
                    "entry_price": round(pos["entry_price"], 3),
                    "exit_date": ds,
                    "exit_price": round(sell_px, 3),
                    "hold_days": di - pos["entry_idx"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl / pos["cost"] * 100, 2),
                    "signal": pos["signal"],
                    "exit_reason": pos["pending_exit"],
                })
                cash += proceeds
                del positions[code]
                continue
            # 收盘判断离场
            pc = bar["prev_close"]
            c = bar["close"]
            if c < pc:
                pos["pending_exit"] = "break_prev_close"
            elif c < pos["entry_price"] * (1 - stop_pct):
                pos["pending_exit"] = "hard_stop"
            elif (di - pos["entry_idx"]) >= 60:
                pos["pending_exit"] = "max_hold"

        # ── ② 开仓(有信号且持仓未满) ──
        for code, df in sig_dfs.items():
            if code in positions:
                continue
            if len(positions) >= max_positions:
                break
            bar = data[code].get(ds)
            if bar is None:
                continue
            if entry_mode == "same_close":
                has_sig = bar["signal"]
                buy_px = bar["close"]
                sig_label = "A" if bar["signal_A"] else "B"
            else:  # next_open: 用前一日信号
                prev_ds = date_list[di - 1] if di > 0 else None
                prev_bar = data[code].get(prev_ds) if prev_ds else None
                if prev_bar is None or not prev_bar["signal"]:
                    continue
                has_sig = True
                buy_px = bar["open"]
                sig_label = "A" if prev_bar["signal_A"] else "B"
            if not has_sig or buy_px <= 0:
                continue
            # 目标仓位: 剩余现金充足才买(等权)
            budget = min(target_value, cash * 0.98)
            shares = int(budget / buy_px / 100) * 100
            if shares < 100 or budget < buy_px * 100:
                continue
            cost = buy_px * shares
            if cost > cash:
                continue
            positions[code] = {
                "entry_date": pd.Timestamp(ds), "entry_price": buy_px,
                "shares": shares, "cost": cost, "entry_idx": di,
                "signal": sig_label,
            }
            cash -= cost

        # ── 权益记录 ──
        total_equity = cash
        for code, pos in positions.items():
            bar = data[code].get(ds)
            if bar:
                total_equity += pos["shares"] * bar["close"]
        equity_curve.append((pd.Timestamp(ds), round(total_equity, 2)))

    # 期末平仓
    for code, pos in list(positions.items()):
        last_bar = data[code].get(date_list[-1])
        if last_bar:
            proceeds = last_bar["close"] * pos["shares"]
            pnl = proceeds - pos["cost"]
            trades.append({
                "code": code,
                "entry_date": str(pos["entry_date"])[:10],
                "entry_price": round(pos["entry_price"], 3),
                "exit_date": date_list[-1],
                "exit_price": round(last_bar["close"], 3),
                "hold_days": len(date_list) - 1 - pos["entry_idx"],
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl / pos["cost"] * 100, 2),
                "signal": pos["signal"],
                "exit_reason": "period_end",
            })
            cash += proceeds

    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "final_equity": round(cash, 2),
        "capital": capital,
    }


def performance(result: dict) -> dict:
    trades = result["trades"]
    capital = result["capital"]
    n = len(trades)
    if n == 0:
        return {"trades": 0, "note": "无交易"}

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    nw, nl = len(wins), len(losses)

    total_pnl = sum(pnls)
    equity = np.array([e for _, e in result["equity_curve"]])
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak * 100
    max_dd = float(np.min(dd)) if len(dd) > 1 else 0.0

    # 年化收益（按权益曲线跨度）
    dates = [d for d, _ in result["equity_curve"]]
    days = (dates[-1] - dates[0]).days if len(dates) > 1 else 1
    growth = equity[-1] / capital
    annual = (growth ** (365.0 / max(days, 1)) - 1) * 100 if growth > 0 else -100

    # 夏普（日收益）
    rets = np.diff(equity) / equity[:-1] if len(equity) > 1 else np.array([0])
    sharpe = float(np.mean(rets) / np.std(rets) * np.sqrt(252)) if np.std(rets) > 1e-12 else 0.0

    gross_win = sum(wins)
    gross_loss = sum(losses)
    profit_factor = gross_win / abs(gross_loss) if gross_loss != 0 else (99.0 if gross_win > 0 else 0.0)
    avg_win = gross_win / nw if nw else 0
    avg_loss = gross_loss / nl if nl else 0
    payoff = avg_win / abs(avg_loss) if avg_loss != 0 else 0.0

    # 信号类型分布
    from collections import Counter
    sig_dist = Counter(t["signal"] for t in trades)
    exit_dist = Counter(t["exit_reason"] for t in trades)

    return {
        "trades": n, "wins": nw, "losses": nl,
        "win_rate": round(nw / n * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "return_pct": round(total_pnl / capital * 100, 2),
        "annual_return_pct": round(annual, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe": round(sharpe, 2),
        "profit_factor": round(profit_factor, 2),
        "payoff_ratio": round(payoff, 2),
        "avg_hold_days": round(np.mean([t.get("hold_days", t.get("hold_bars", 0)) for t in trades]), 1),
        "signal_dist": dict(sig_dist),
        "exit_dist": dict(exit_dist),
    }


def format_report(perf: dict, code: str = "") -> str:
    if perf.get("trades", 0) == 0:
        return f"{code}: 无交易"
    return (
        f"{code}  {perf['trades']}笔 | 胜率{perf['win_rate']}% ({perf['wins']}胜/{perf['losses']}负) | "
        f"收益{perf['return_pct']:+.1f}% (年化{perf['annual_return_pct']:+.0f}%) | "
        f"最大回撤{perf['max_drawdown_pct']}% | 夏普{perf['sharpe']} | "
        f"盈亏比{perf['payoff_ratio']} | 利润因子{perf['profit_factor']} | "
        f"均持{perf['avg_hold_days']}天"
    )


# ══════════════════════════════════════════════════════════════
# 5. 主流程
# ══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="昨收价极简交易体系回测")
    ap.add_argument("--codes", default="600519,000858,601318,000831,002589",
                    help="股票代码,逗号分隔")
    ap.add_argument("--years", type=int, default=2, help="回测年数")
    ap.add_argument("--capital", type=float, default=100_000, help="初始资金/标的")
    ap.add_argument("--mode", choices=["next_open", "same_close", "minute", "multitf", "portfolio"], default="next_open",
                    help="next_open=次日开盘买 / same_close=当日收盘买 / minute=分钟级 / multitf=多周期共振 / portfolio=组合回测(多标的共享资金)")
    ap.add_argument("--tf", choices=["m5", "m15", "m30"], default="m15",
                    help="分钟模式的时间框架(默认m15=15分钟)")
    ap.add_argument("--stop", type=float, default=0.08, help="硬止损百分比(默认8%%)")
    args = ap.parse_args()

    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    days = args.years * 250 + 50
    print(f"═══ 昨收价极简交易体系回测 ═══")
    print(f"标的: {codes} | 周期: {args.years}年 | 资金/标的: {args.capital:,.0f}元 | "
          f"买入模式: {args.mode} | 硬止损: {args.stop:.0%}")

    all_trades = []
    is_portfolio = args.mode == "portfolio"
    portfolio_sigs = {}  # code -> 加信号列df (组合模式收集用)

    for code in codes:
        is_minute = args.mode == "minute"
        is_multitf = args.mode == "multitf"
        try:
            if is_multitf:
                # 三周期: 日线(位置/方向) + m1(开盘3分钟) + m15(盘中执行)
                df_day = fetch_kline(code, max(days, 100))
                df_m1 = fetch_kline(code, 2000, tf="m1")
                df = fetch_kline(code, 2000, tf="m15")
            elif is_minute:
                # 分钟模式: 约6个交易日数据(腾讯单次最多返回~2000根)
                df = fetch_kline(code, 2000, tf=args.tf)
            else:
                df = fetch_kline(code, days)
        except Exception as e:
            print(f"✗ {code}: 数据获取失败 {e}")
            continue
        if df.empty or len(df) < 100:
            print(f"✗ {code}: K线不足({len(df)}行)")
            continue
        df.attrs["code"] = code

        # ── 组合模式: 收集信号, 循环结束后统一回测 ──
        if is_portfolio:
            sig_df = generate_signals(df)
            portfolio_sigs[code] = sig_df
            print(f"  ✓ {code}: {int(sig_df['signal'].sum())}个信号, {len(sig_df)}根K线")
            continue

        if is_multitf:
            result = backtest_multitf(df_m1, df, df_day, capital=args.capital,
                                      stop_pct=min(args.stop, 0.05))
            perf = performance(result)
            all_trades.extend(result["trades"])
            print(format_report(perf, code))
            print(f"    数据: 日线{len(df_day)}根 + m1{len(df_m1)}根 + m15{len(df)}根")
            from collections import Counter
            if result["trades"]:
                print(f"    位置分布: {dict(Counter(t.get('pos_level','?') for t in result['trades']))} | "
                      f"开盘基调: {dict(Counter(t.get('bias','?') for t in result['trades']))}")
            for t in result["trades"][-3:]:
                print(f"      {t['entry_date']}→{t['exit_date']} 买{t['entry_price']} 卖{t['exit_price']} "
                      f"{t['pnl_pct']:+.1f}% [{t['signal']}信号/{t['exit_reason']}]")
            continue

        if is_minute:
            bars_per_day = {"m5": 48, "m15": 16, "m30": 8}.get(args.tf, 16)
            result = backtest_minute(df, capital=args.capital, bars_per_day=bars_per_day,
                                     stop_pct=min(args.stop, 0.05))
            perf = performance(result)
            all_trades.extend(result["trades"])
            print(format_report(perf, code))
            print(f"    数据: {len(df)}根{args.tf}bar | {len(df)//bars_per_day}个交易日")
            for t in result["trades"][-3:]:
                print(f"      {t['entry_date']}→{t['exit_date']} 买{t['entry_price']} 卖{t['exit_price']} "
                      f"{t['pnl_pct']:+.1f}% [{t['signal']}信号/{t['exit_reason']}]")
            continue

        sig_df = generate_signals(df)

        # 形态分布统计
        pat_dist = sig_df["pattern"].value_counts().to_dict()
        n_sig = int(sig_df["signal"].sum())

        result = backtest_single(sig_df, capital=args.capital,
                                 entry_mode=args.mode, stop_pct=args.stop)
        perf = performance(result)
        all_trades.extend(result["trades"])

        print(format_report(perf, code))
        print(f"    形态分布: {pat_dist} | 信号数: {n_sig}")
        # 最近3笔交易明细
        for t in result["trades"][-3:]:
            print(f"      {t['entry_date']}→{t['exit_date']} 买{t['entry_price']} 卖{t['exit_price']} "
                  f"{t['pnl_pct']:+.1f}% [{t['signal']}信号/{t['exit_reason']}]")

    # ── 组合回测执行 ──
    if is_portfolio and portfolio_sigs:
        print(f"\n═══ 组合回测 ({len(portfolio_sigs)}标的 共享资金 {args.capital:,.0f}元) ═══")
        result = backtest_portfolio(portfolio_sigs, capital=args.capital,
                                    max_positions=3, stop_pct=args.stop,
                                    entry_mode=args.mode if args.mode != "portfolio" else "next_open")
        perf = performance(result)
        all_trades = result["trades"]
        # 组合权益曲线
        eq = np.array([e for _, e in result["equity_curve"]])
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak) / peak * 100
        print(f"组合: {perf['trades']}笔 | 胜率{perf['win_rate']}% | "
              f"收益{perf['return_pct']:+.1f}% | 最大回撤{dd.min():.1f}% | "
              f"夏普{perf['sharpe']} | 盈亏比{perf['payoff_ratio']} | "
              f"利润因子{perf['profit_factor']}")
        print(f"期末权益: {result['final_equity']:,.0f}元 (资金{args.capital:,.0f}元)")
        from collections import Counter
        print(f"信号分布: {dict(Counter(t['signal'] for t in result['trades']))} | "
              f"离场分布: {dict(Counter(t['exit_reason'] for t in result['trades']))}")
        print(f"各标的表现:")
        for code in portfolio_sigs:
            sub = [t for t in result['trades'] if t['code'] == code]
            if sub:
                pnl = sum(t['pnl'] for t in sub)
                wins = sum(1 for t in sub if t['pnl'] > 0)
                print(f"  {code}: {len(sub)}笔 {pnl:+,.0f}元 胜率{wins/len(sub)*100:.0f}%")
        print(f"\n最近8笔交易:")
        for t in result["trades"][-8:]:
            print(f"  {t['entry_date']}→{t['exit_date']} {t['code']} 买{t['entry_price']} 卖{t['exit_price']} "
                  f"{t['pnl_pct']:+.1f}% [{t['signal']}信号/{t['exit_reason']}]")
        return

    # 汇总
    if all_trades:
        combined = {
            "trades": all_trades,
            "capital": args.capital * len(codes),
            "equity_curve": [],
            "final_equity": args.capital * len(codes) + sum(t["pnl"] for t in all_trades),
        }
        # 简易汇总(等权各标的独立)
        tot_pnl = sum(t["pnl"] for t in all_trades)
        wins = sum(1 for t in all_trades if t["pnl"] > 0)
        n = len(all_trades)
        print(f"\n═══ 汇总 ({len(codes)}标的) ═══")
        print(f"总交易 {n}笔 | 胜率 {wins/n*100:.1f}% | 总盈亏 {tot_pnl:+,.0f}元 "
              f"({tot_pnl/(args.capital*len(codes))*100:+.1f}%)")
        from collections import Counter
        print(f"信号分布: {dict(Counter(t['signal'] for t in all_trades))}")
        print(f"离场分布: {dict(Counter(t['exit_reason'] for t in all_trades))}")


if __name__ == "__main__":
    main()
