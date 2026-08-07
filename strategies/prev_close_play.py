# -*- coding: utf-8 -*-
"""昨收价极简战法 v1.0 — 融入工作流的信号模块
战法核心: 只盯"昨日收盘价"一个数字
- 买点A(挖坑转强): 低开+盘中跌破昨收+收盘收回站稳 → 洗盘结束
- 买点B(强势延续): 站稳开盘+回踩不破昨收+收阳(非涨停) → 多头延续
- 防骗线: 日线级用"收盘确认"近似(等效15分钟有效站稳)
- 离场由持仓监控执行(跌破昨收即卖出), 本模块只产生买入信号
"""
import logging
import numpy as np
logger = logging.getLogger("aurora.prev_close")


def check_prev_close(kline_df) -> dict:
    """昨收价战法信号检测
    Args:
        kline_df: 日线K线DataFrame({date,open,close,high,low,volume})
    Returns:
        {"signal": bool, "score": int, "type": "A"/"B", "desc": str, "prev_close": float}
    """
    if kline_df is None or len(kline_df) < 20:
        return {"signal": False, "score": 0, "type": "", "desc": "K线不足", "prev_close": 0}

    close = kline_df["close"].values
    open_ = kline_df["open"].values
    low = kline_df["low"].values
    high = kline_df["high"].values
    vol = kline_df["volume"].values

    # 昨收 = 前一交易日收盘
    prev_close = close[-2] if len(close) >= 2 else 0
    if prev_close <= 0:
        return {"signal": False, "score": 0, "type": "", "desc": "无昨收", "prev_close": 0}

    o, c, l, h, v = open_[-1], close[-1], low[-1], high[-1], vol[-1]
    chg_pct = (c - prev_close) / prev_close * 100

    # ── 买点A: 挖坑转强 (低开 + 盘中跌破昨收 + 收盘收回站稳) ──
    buy_A = (o < prev_close) and (l < prev_close) and (c > prev_close)
    # ── 买点B: 强势延续 (站稳开盘 + 回踩不破 + 收阳) 且非涨停 ──
    limit_up = chg_pct >= 9.5 and o == c  # 一字涨停无法买入
    buy_B = (o >= prev_close) and (l >= prev_close) and (c > prev_close) \
            and (chg_pct < 9.0) and not limit_up

    if buy_A:
        # 收回强度: 收盘相对昨收的幅度 + 放量确认
        recover = (c - prev_close) / prev_close * 100
        vol_ratio = v / (np.mean(vol[-21:-1]) + 1e-9) if len(vol) > 21 else 1.0
        score = int(60 + min(recover * 5, 20) + min(max(vol_ratio - 1, 0) * 10, 20))
        return {"signal": True, "score": min(score, 95), "type": "A",
                "desc": f"挖坑转强:低开{o:.2f}破昨收{prev_close:.2f}收回{c:.2f}(+{recover:.1f}%)",
                "prev_close": round(prev_close, 3)}
    if buy_B:
        strength = (c - prev_close) / prev_close * 100
        score = int(55 + min(strength * 5, 25))
        return {"signal": True, "score": min(score, 95), "type": "B",
                "desc": f"强势延续:站稳昨收{prev_close:.2f}回踩不破收阳(+{strength:.1f}%)",
                "prev_close": round(prev_close, 3)}

    return {"signal": False, "score": 0, "type": "", "desc": "无昨收价买点", "prev_close": round(prev_close, 3)}


def check_prev_close_exit(kline_df, entry_price: float) -> dict:
    """持仓离场检查 — 昨收价体系离场铁律:
    ① 跌破昨收无法收回 → 卖出(核心)
    ② 硬止损: 收盘 < 买入价×(1-5%)
    ③ 假突破识别: 盘中跌破昨收但收盘收回 → 持有(洗盘)
    Returns:
        {"exit": bool, "reason": str, "price": float}
    """
    if kline_df is None or len(kline_df) < 3:
        return {"exit": False, "reason": "", "price": 0}
    close = kline_df["close"].values
    prev_close = close[-2]
    c = close[-1]
    l = kline_df["low"].values[-1]
    o = kline_df["open"].values[-1]

    if c < prev_close:
        # 收盘跌破昨收 = 有效破位(收盘确认, 防盘中假跌破)
        return {"exit": True, "reason": f"跌破昨收{prev_close:.2f}", "price": c}
    if entry_price > 0 and c < entry_price * 0.95:
        return {"exit": True, "reason": f"硬止损-5%", "price": c}
    return {"exit": False, "reason": "", "price": 0}
