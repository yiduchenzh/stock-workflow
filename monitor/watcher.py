"""持仓监控 — 止损止盈+移动止盈+分批止盈 (使用executor版SimAccount)"""
import json, logging
from pathlib import Path
from datetime import datetime
from data.sources import get_tencent_quotes
from risk.trailing import calc_trailing_stop, should_scale_out
logger = logging.getLogger("aurora.watch")

_trailing_stops: dict[str, float] = {}
_trailing_highs: dict[str, float] = {}  # v14.46: 入场以来最高价(ATR回撤基准)

def watch_positions(positions: dict, cfg: dict, kline_cache: dict = None) -> list:
    """持仓监控 — 止损止盈+移动止盈+分批止盈。整个函数体含异常兜底

    v14.46 修复(老仓移动止盈审计): ATR增强原来是死代码——calc_trailing_stop
    调用没传klines, 且最高价只用current_price(缺入场以来最高价, ATR回撤基准错)。
    现在: ① 传kline_cache启用ATR增强 ② _trailing_highs跟踪入场以来最高价。

    v14.50 修复(2026-09-04 周复盘 P0-A/P1-B):
    ③ 最高价锚点只取【entry_date之后】的K线高点——原取近60日最高(含入场前),
       买入回调股时 highest 远高于成本 → ATR回撤位虚高 → 次日开盘即 breach 清仓。
    ④ 持仓<min_hold_days 不设移动止盈线(只做硬止损)——防趋势仓被洗出。
    """
    try:
        if not positions: return []
        codes = list(positions.keys())
        quotes = get_tencent_quotes(codes)
        alerts = []
        risk_cfg = cfg.get("risk", {})
        # 修复P0(v14.44): 单位bug — stop_loss_pct来自trader_types是小数(0.05=5%),
        # 原代码/100再乘导致止损距离0.05%(噪声洗出)。修正: 小数直接用。
        profile_sl = risk_cfg.get("stop_loss_pct", None)
        hard_pct = risk_cfg.get("stop_loss", {}).get("hard_pct", 5.0)
        # hard_pct是百分数(5.0=5%)需/100; profile_sl是小数(0.05=5%)直接用
        if profile_sl is not None:
            stop_loss_pct = profile_sl  # 小数: 0.05 = 5%
        else:
            stop_loss_pct = hard_pct / 100.0  # 百分数转小数
        # v14.50: 最小持仓天数 — 期间只做硬止损, 不激活移动止盈(让利润奔跑)
        # 来源优先级: cfg.risk.min_hold_days → profile风格(max_hold//3) → 默认3
        min_hold_days = int(risk_cfg.get("min_hold_days", 0) or 0)
        if min_hold_days <= 0:
            _amhd = int(risk_cfg.get("max_hold_days", 0) or 0)
            min_hold_days = max(1, _amhd // 3) if _amhd > 0 else 3
        today = datetime.now().date()
        for code, pos in positions.items():
            q = quotes.get(code, {})
            cur = q.get("price", pos.get("current_price", pos.get("avg_cost", 0)))
            entry = pos.get("avg_cost", cur)

            sl = pos.get("stop_loss", entry * (1 - stop_loss_pct))
            if cur <= sl:
                alerts.append({"type": "stop_loss", "code": code, "price": cur, "stop": sl})
                _trailing_stops.pop(code, None)
                _trailing_highs.pop(code, None)
                continue

            tp = pos.get("take_profit", entry * 1.10)
            if cur >= tp:
                alerts.append({"type": "take_profit", "code": code, "price": cur, "target": tp})

            # v14.50: min_hold保护 — 持仓天数不足只做硬止损(上面已检查), 跳过trailing
            held_days = 0
            ed = str(pos.get("entry_date") or "")[:10]
            if ed:
                try:
                    held_days = (today - datetime.strptime(ed, "%Y-%m-%d").date()).days
                except Exception:
                    held_days = 0
            if held_days < min_hold_days:
                _trailing_stops.pop(code, None)
                _trailing_highs.pop(code, None)
                continue

            profit_pct = (cur - entry) / entry * 100
            current_ts = _trailing_stops.get(code, 0.0)
            # v14.46/v14.50: 入场以来最高价跟踪(ATR回撤基准) — 只取 entry_date 之后的K线
            kdf = (kline_cache or {}).get(code) if kline_cache else None
            kline_high = 0.0
            if kdf is not None and not getattr(kdf, "empty", True):
                try:
                    import numpy as _np
                    # 兼容: date列 或 DatetimeIndex / str index
                    dates = None
                    if "date" in (getattr(kdf, "columns", None) or []):
                        dates = [str(x)[:10] for x in kdf["date"]]
                    elif getattr(kdf, "index", None) is not None:
                        dates = [str(x)[:10] for x in kdf.index]
                    if dates and ed:
                        vals = [h for d, h in zip(dates, kdf["high"].values) if d >= ed]
                        if vals:
                            kline_high = float(max(vals))
                except Exception:
                    pass
            highest = max(cur, kline_high, _trailing_highs.get(code, 0.0))
            _trailing_highs[code] = highest
            new_ts = calc_trailing_stop(entry, cur, current_ts, klines=kdf, market_regime=cfg.get("market", {}).get("default_regime", "range"), highest_price=highest, profile_name=cfg.get("profile_name"))

            if new_ts > current_ts and new_ts > 0:
                _trailing_stops[code] = new_ts
                # v14.50: 抬线只发状态日志, 不再append卖出型告警
                #   (engine侧曾把type=trailing_stop当卖单执行 → 次日批量清仓的P0根因)
                logger.info(f"  [Trailing] {code}: stop raised to {new_ts:.4f} (profit {profit_pct:.1f}%, held {held_days}d)")

            if current_ts > 0 and cur <= current_ts:
                alerts.append({
                    "type": "breach_stop", "code": code,
                    "price": cur, "trailing_stop": round(current_ts, 4),
                    "profit_pct": round(profit_pct, 2)
                })
                logger.warning(f"  [Breach] {code}: price {cur:.4f} hit trailing stop {current_ts:.4f}")
                _trailing_stops.pop(code, None)
                _trailing_highs.pop(code, None)

        return alerts
    except Exception as e:
        logger.error(f"[Watcher] watch_positions 异常兜底: {e}", exc_info=True)
        return []