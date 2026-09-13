# -*- coding: utf-8 -*-
""""至简交易法"回测引擎 — 老陈实盘战法（独立新增, 不破坏任何现有模块）。

════════════════════════════════════════════════════════════════════
战法来源
════════════════════════════════════════════════════════════════════
老陈 5 条实盘规则:

  ① 开仓前提（全局约束）: 前日股票收盘价 > MA5 才允许当日开仓。
  ② 情形1【高开/平开 + 低走】: 开盘价≥昨收, 盘中走低。
       买点 = 价格回抽 > 当日开盘价;  卖点 = 持仓中回抽 < 当日开盘价。
  ③ 情形2【高开/平开 + 高走】: 开盘价≥昨收, 盘中走高。
       买点 = 回落 > 当日开盘价;     卖点 = 不创新高 且 回落 < 当日开盘价。
  ④ 情形3【低开 + 低走, 但不小于昨最低】: 开盘价<昨收, 低走, 日内低点不低于昨日最低(相对强)。
       买点 = 回抽 > 当日开盘价;      卖点 = 回抽不创新高 且 < 当日开盘价。
  ⑤ 情形4【低开 + 高走, 创新高】: 开盘价<昨收, 高走, 并创出新高(日内/相对昨高)。
       买点 = 回落 > 当日开盘价;      卖点 = 不创新高 且 回落 < 当日开盘价。

════════════════════════════════════════════════════════════════════
每日术语（分钟级逐bar）
════════════════════════════════════════════════════════════════════
  · open_day   = 当日第一根bar的 open（当日开盘价）
  · prev_close = 前一日日K close（昨收）
  · prev_low   = 前一日日K low （昨最低）
  · prev_high  = 前一日日K high（昨最高）
  · MA5        = 过去5个交易日 close 的简单均值（截止前一日, 即昨收那5天）
  · 高开/平开:  open_day >= prev_close ;   低开: open_day < prev_close
  · 低走:  盘中曾跌破开盘价 (low_sofar < open_day)
  · 高走:  盘中创出高于开盘价的新高 (high_sofar > open_day)

════════════════════════════════════════════════════════════════════
转译成的"无歧义逐bar触发规则"（★ 核心, 每条标注对应老陈原话）
════════════════════════════════════════════════════════════════════
逐bar从当日第一根向后扫描, 维护当日 running_high / running_low。

【买点 Buy —— 统一触发条件, bar收盘判断 → 下一根bar开盘成交(无未来函数)】
  Buy bar : bar.close > open_day  且  bar.low <= open_day
  即"该bar盘中回踩到当日开盘价(或曾跌破), 收盘又站稳在开盘价上方"
  → 这正是老陈说的"回抽/回落 > 当日开盘价买":
       情形1 (高开低走, 回抽)   —— 价格从开盘价下方回抽突破 open_day,
                                   该bar low 必然<= open_day 且 close>open_day。
       情形2 (高开高走, 回落)   —— 高走中某bar回落到 open_day (low<=open_day)
                                   又收稳上方 (close>open_day)。
       情形3 (低开低走不破昨低, 回抽) —— 同上, 回抽突破 open_day。
       情形4 (低开高走创新高, 回落) —— 高走中回落到 open_day 又收稳。
  保守策略: 只认"回踩开盘价且收盘站稳"这一根bar, 不凭空制造买卖点。
  开仓前提(①): 仅当 前日收盘 > MA5 的当日才允许触发买入; 否则整日禁买。

【卖点 Sell —— 统一触发条件, bar收盘判断 → 下一根bar开盘成交】
  Sell bar : bar.close < open_day  且  bar.high <= 该bar之前当日 running_high
  即"该bar未创日内新高(不创新高) 且 收盘跌破当日开盘价(回抽/回落<开盘价)"
  → 对应老陈卖点:
       情形1 (回抽<开盘价卖)      —— 持仓中回抽跌破 open_day。
       情形2 (不创新高且回落<开盘价卖) —— 回落跌破 open_day 且该bar不创新高。
       情形3 (回抽不创新高且<开盘价卖)。
       情形4 (不创新高且回落<开盘价卖)。
  保守: 一根创新高的bar(high>当日之前最高)即使收在开盘价下方也不在此触发
        (极端盘中新高又收绿属于形态混杂, 宁可不卖, 待后续破位bar)。★从严★

【持仓结束】
  同一时间最多持仓1只。当日开仓后:
    - 触发卖点 → 下一bar开盘平仓（当日平仓）。
    - 若当日结束仍未触发卖点 → 当日最后一根bar收盘价强制平仓（当日平仓）。
  （符合"当日开仓当日或隔日平仓"的保守口径; 本实现取"当日平仓"最简形态,
    使 per_day 每一交易日对应一笔完整 round-trip, P&L 清晰无跨日持仓歧义。）

【当日情形打标（用于 per_day.scenario / scenario_breakdown）】
  每一交易的完整日K走完后, 按下述优先级确定性归类:
    opens_high = open_day >= prev_close
    opens_low  = open_day <  prev_close
    dipped     = 当日最低 < open_day      （盘中跌破开盘价 = 低走）
    made_high  = 当日最高 > open_day      （盘中创出高于开盘价的新高 = 高走/创新高）
    情形1: opens_high 且 dipped                                （高开低走）
    情形2: opens_high 且 (not dipped)                          （高开高走）
    情形3: opens_low 且 dipped 且 当日最低 >= prev_low         （低开低走不破昨低）
    情形4: opens_low 且 made_high                              （低开高走创新高）
    若 opens_low 且 made_high 与 dipped 并存 → 以 made_high 优先记为情形4;
    若 opens_low 且 当日最低 < prev_low（跌破昨低）且 not made_high
        → 不属于老陈四种情形（相对弱）, 当日不交易。

数据口径:
  - 分钟K 用 prev_close_strategy.fetch_kline(code, bars, tf) 拉取（复用, 不改）。
  - 日K   用同一 fetch_kline(code, days, tf="day") 拉取, 计算 MA5 / 昨收 / 昨低 / 昨高。
  - 成本   复用 prev_close_strategy._trade_cost + COMMISSION/MIN_COMMISSION/
           STAMP_TAX/TRANSFER_FEE（佣金万3 min5 + 卖出印花千1 + 沪/北过户万0.2）。
  - 无未来函数: 一律 bar 收盘判断 → 下一根bar开盘价成交（pending 模式）。
  - 结果级缓存: 复用 data.result_cache.ResultCache + make_bt_key（独立缓存文件）。

用法:
  from data.zhijian_backtest import run_zhijian
  r = run_zhijian("300319", tf="m15", capital=100_000)
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from prev_close_strategy import (  # noqa: E402
    COMMISSION, MIN_COMMISSION, STAMP_TAX, TRANSFER_FEE,
    _df_fingerprint, _market_of, _trade_cost, fetch_kline,
)
from data.result_cache import ResultCache, make_bt_key  # noqa: E402


def _json_safe(value):
    """把回测结果递归归一化为 JSON 可序列化结构 (numpy 标量 → python 原生)。"""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, np.ndarray):
        return [_json_safe(v) for v in value.tolist()]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value

# 独立缓存文件, 不复用 prevclose / bt_full, 互不干扰
_ZJ_CACHE = ResultCache(Path(__file__).resolve().parent / "zhijian_result_cache.json")

CACHE_ENABLED = True
BUST_CACHE = False

ML5 = 5  # MA5 周期


# ────────────────────────────────────────────────────────────────
# 1. 数据准备: 日K → 每交易日 {prev_close, prev_low, prev_high, ma5, gate}
# ────────────────────────────────────────────────────────────────
def _daily_meta(daily: pd.DataFrame) -> dict:
    """从日线构造 {date→{prev_close,prev_high,prev_low,ma5,gate}}。

    gate(开仓前提 ①) = 截止昨收的 MA5 均值 < 昨收, 即 close[T-1] > mean(close[T-5..T-1])。
    """
    d = daily.sort_values("date").reset_index(drop=True)
    closes = d["close"].astype(float).values
    highs = d["high"].astype(float).values
    lows = d["low"].astype(float).values
    dates = pd.to_datetime(d["date"]).dt.date.values
    ma5 = pd.Series(closes).rolling(ML5).mean().values
    out = {}
    for i in range(1, len(d)):
        out[str(dates[i])] = {
            "prev_close": float(closes[i - 1]),
            "prev_high": float(highs[i - 1]),
            "prev_low": float(lows[i - 1]),
            "ma5": float(ma5[i - 1]),
            # 开仓前提: 前日收盘 > MA5(截止昨收) 才允许当日买入
            "gate": bool(closes[i - 1] > ma5[i - 1]),
        }
        # 前一日即5日窗口, ma5[i-1] 当 i-1>=4 才有值; i<5 无 MA5 → 保守禁买
        if np.isnan(ma5[i - 1]):
            out[str(dates[i])]["gate"] = False
    return out


def _classify_scenario(open_day, prev_close, prev_low, run_high, run_low) -> str | None:
    """按"买入时点"的前瞻状态确定性归类四情形。

    老陈四情形的分野在【开盘方向】+【买点前的走势方向】:
      · 高开/平开 (open_day >= prev_close):
          情形1 = 买点前已跌破开盘价(低走, 回抽买)  → run_low < open_day
          情形2 = 买点前未跌破开盘价(高走, 回落买)  → run_low >= open_day
      · 低开   (open_day <  prev_close):
          情形4 = 买点前已创高于开盘价新高(高走创新高, 回落买) → run_high > open_day
          情形3 = 买点前未创新高(低走, 回抽买, 且日内低点不破昨低) → run_high <= open_day
    因此用"买点bar之前"的 running_high / running_low 判定, 无未来函数(只用已走完的bar)。
    返回 None 表示不构成可交易情形(低开低走破昨低等)。
    """
    opens_high = open_day >= prev_close
    opens_low = open_day < prev_close

    if opens_high:
        # 情形1 高开低走(回抽) / 情形2 高开高走(回落)
        return "scenario1" if run_low < open_day else "scenario2"

    # 低开
    if run_high > open_day:
        return "scenario4"               # 低开高走创新高(回落买)
    if run_low >= prev_low:
        return "scenario3"               # 低开低走不破昨低(回抽买)
    # 低开低走但跌破昨低 → 老陈无此情形(相对弱) → 不交易
    return None


# ────────────────────────────────────────────────────────────────
# 2. 核心回测
# ────────────────────────────────────────────────────────────────
def backtest_zhijian(df_min: pd.DataFrame, daily: pd.DataFrame,
                     capital: float = 100_000) -> dict:
    """分钟级"至简交易法"回测。

    入参:
      df_min  分钟K {date(含日期时间), open, close, high, low, volume}, 升序。
      daily   日K   {date, open, high, low, close}, 用于 MA5 / 昨收昨低昨高。
    返回完整结果 dict(见模块 docstring / run_zhijian)。
    """
    code = daily.attrs.get("code", "?")

    # ---- 结果级缓存 ----
    key = None
    if CACHE_ENABLED:
        key = make_bt_key({
            "mode": "zhijian", "capital": capital,
            "fp_min": _df_fingerprint(df_min), "fp_day": _df_fingerprint(daily),
        })
        if not BUST_CACHE:
            cached = _ZJ_CACHE.get(key)
            if cached is not None:
                return cached

    minfo = _daily_meta(daily)
    if not minfo:
        raise ValueError("日K不足, 无法计算 MA5/昨收")

    m = df_min.sort_values("date").reset_index(drop=True)
    dates = pd.to_datetime(m["date"])
    opens = m["open"].astype(float).values
    highs = m["high"].astype(float).values
    lows = m["low"].astype(float).values
    closes = m["close"].astype(float).values
    day_key = dates.dt.date.astype(str).values

    # 按交易日分组
    days = []
    day_order = []
    for i in range(len(m)):
        dk = day_key[i]
        if not day_order or day_order[-1] != dk:
            day_order.append(dk)
            days.append([i])
        else:
            days[-1].append(i)

    trades = []            # 每笔 {date, entry_px, exit_px, fee, pnl, scenario}
    per_day = []           # 每交易日 {date, open_day, scenario, buy_px, exit_px, pnl}
    scenario_cnt = {"scenario1": 0, "scenario2": 0, "scenario3": 0, "scenario4": 0}
    cash = capital

    # 逐日处理
    for dk, idx in zip(day_order, days):
        if dk not in minfo:
            continue
        info = minfo[dk]
        prev_close = info["prev_close"]
        prev_low = info["prev_low"]
        gate = info["gate"]

        first = idx[0]
        open_day = opens[first]

        # ----- 当日逐bar扫描 (bar收盘判断 → 下一bar开盘成交, 无未来函数) -----
        pending = None        # {"buy"/"sell"}
        entry_px = None
        entry_shares = None
        cur_scenario = None   # 当前持仓对应情形(买入时点判定)
        run_high = open_day
        run_low = open_day

        for j, bar_i in enumerate(idx):
            # ① 先执行上一bar收盘触发的动作(下一bar开盘成交)
            if pending is not None:
                act, p_scenario = pending
                pending = None
                if act == "buy":
                    if entry_px is None:
                        buy_px = opens[bar_i]
                        if buy_px > 0:
                            shares = int(cash * 0.98 / buy_px / 100) * 100
                            if shares >= 100:
                                fee_buy = _trade_cost(buy_px, shares, is_buy=True,
                                                      code=code)["total"]
                                entry_px = buy_px
                                entry_shares = shares
                                entry_cost = buy_px * shares + fee_buy
                                cash -= entry_cost
                                cur_scenario = p_scenario
                else:  # sell
                    if entry_shares is not None:
                        sell_px = opens[bar_i]
                        if sell_px > 0:
                            fee_sell = _trade_cost(sell_px, entry_shares,
                                                   is_buy=False, code=code)["total"]
                            net = sell_px * entry_shares - fee_sell
                            # 总成本 = 买入价×股数 + 买入佣金 + 卖出费用(印花/佣金/过户)
                            buy_fee_was = _trade_cost(entry_px, entry_shares,
                                                      is_buy=True, code=code)["total"]
                            total_cost = entry_px * entry_shares + buy_fee_was
                            pnl = net - total_cost
                            trades.append({
                                "date": dk, "side": "round",
                                "buy_px": round(entry_px, 3),
                                "exit_px": round(sell_px, 3),
                                "shares": entry_shares,
                                "fee": round(buy_fee_was + fee_sell, 2),
                                "pnl": round(pnl, 2),
                                "scenario": cur_scenario,
                            })
                            per_day.append({
                                "date": dk, "open_day": round(open_day, 3),
                                "scenario": cur_scenario, "buy_px": round(entry_px, 3),
                                "exit_px": round(sell_px, 3), "pnl": round(pnl, 2),
                            })
                            scenario_cnt[cur_scenario] = scenario_cnt.get(
                                cur_scenario, 0) + 1
                            cash += net
                    entry_px = None
                    entry_shares = None
                    cur_scenario = None

            # ② 当前bar前的 running_high/low (供分类/不创新高判定, 只用已走完bar)
            rhi = run_high
            rlo = run_low

            # ③ 收盘判断: 买卖触发 (无未来函数核心 — 下一bar才成交)
            if entry_px is None and not pending:
                # Buy: 该bar回踩到开盘价(low<=open_day) 且 收盘站稳(close>open_day)
                if closes[bar_i] > open_day and lows[bar_i] <= open_day:
                    sc = _classify_scenario(open_day, prev_close, prev_low,
                                            rhi, rlo)
                    # 开仓前提(①): 仅当前日收盘>MA5 才允许开仓
                    if sc is not None and gate:
                        pending = ("buy", sc)
            else:
                # Sell(持仓中): close<open_day 且 该bar不创新高(high<=rhi)
                if (entry_shares is not None and closes[bar_i] < open_day
                        and highs[bar_i] <= rhi):
                    pending = ("sell", None)

            # ④ 更新当日 running_high/low (含当前bar)
            run_high = max(run_high, highs[bar_i])
            run_low = min(run_low, lows[bar_i])

        # ⑤ 当日结束: 若仍持仓, 以当日最后一根bar收盘价强制平仓(当日平仓)
        if entry_shares is not None:
            sell_px = closes[idx[-1]]
            if sell_px > 0:
                fee_sell = _trade_cost(sell_px, entry_shares, is_buy=False,
                                       code=code)["total"]
                net = sell_px * entry_shares - fee_sell
                buy_fee_was = _trade_cost(entry_px, entry_shares, is_buy=True,
                                          code=code)["total"]
                total_cost = entry_px * entry_shares + buy_fee_was
                pnl = net - total_cost
                trades.append({
                    "date": dk, "side": "round",
                    "buy_px": round(entry_px, 3), "exit_px": round(sell_px, 3),
                    "shares": entry_shares, "fee": round(buy_fee_was + fee_sell, 2),
                    "pnl": round(pnl, 2), "scenario": cur_scenario,
                })
                per_day.append({
                    "date": dk, "open_day": round(open_day, 3),
                    "scenario": cur_scenario, "buy_px": round(entry_px, 3),
                    "exit_px": round(sell_px, 3), "pnl": round(pnl, 2),
                })
                scenario_cnt[cur_scenario] = scenario_cnt.get(cur_scenario, 0) + 1
                cash += net
            entry_px = None
            entry_shares = None
            cur_scenario = None

    # ---- 统计 ----
    pnls = [t["pnl"] for t in trades]
    n = len(pnls)
    nw = len([p for p in pnls if p > 0])
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins)
    gross_loss = sum(losses)
    profit_factor = gross_win / abs(gross_loss) if gross_loss else (99.0 if gross_win > 0 else 0.0)
    net_pnl = sum(pnls)
    total_return = net_pnl / capital * 100 if capital else 0.0
    win_rate = round(nw / n * 100, 1) if n else 0.0

    # 权益曲线(逐交易日) → 最大回撤
    eq = capital
    peak = capital
    max_dd = 0.0
    for t in trades:
        eq += t["pnl"]
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (eq - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd

    result = _json_safe({
        "code": code,
        "period": {"tf": None, "trading_days": len(per_day), "trades": n},
        "trades": trades,
        "per_day": per_day,
        "scenario_breakdown": scenario_cnt,
        "stats": {
            "trades": n,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "net_pnl": net_pnl,
            "total_return": total_return,
            "max_drawdown": max_dd,
            "capital": capital,
        },
        "final_equity": cash,
    })

    if CACHE_ENABLED and key is not None:
        _ZJ_CACHE.set(key, result)
    return result


# ────────────────────────────────────────────────────────────────
# 3. 顶层入口
# ────────────────────────────────────────────────────────────────
def fetch_pair(code: str, min_bars: int = 2000, tf: str = "m15",
               day_days: int = 400):
    """拉取 分钟K + 日K 对, 均挂 attrs['code']。"""
    df_min = fetch_kline(code, min_bars, tf=tf)
    daily = fetch_kline(code, day_days, tf="day")
    if df_min is None or daily is None or df_min.empty or daily.empty:
        raise RuntimeError(f"{code}: 分钟K({tf}) 或 日K 拉取失败(网络受限或无此标的)")
    df_min.attrs["code"] = code
    daily.attrs["code"] = code
    return df_min, daily


def run_zhijian(code: str, tf: str = "m15", capital: float = 100_000,
                min_bars: int = 2000, day_days: int = 400) -> dict:
    """高层入口: 拉数据(分钟m15 + 日) → 回测 → 返回完整结果 dict。"""
    df_min, daily = fetch_pair(code, min_bars, tf, day_days)
    result = backtest_zhijian(df_min, daily, capital=capital)
    result["period"] = _json_safe({
        "tf": tf,
        "trading_days": result["period"].get("trading_days"),
        "trades": result["period"].get("trades"),
        "min_bars": len(df_min), "day_bars": len(daily),
    })
    return result


if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "300319"
    res = run_zhijian(code)
    print(res)
