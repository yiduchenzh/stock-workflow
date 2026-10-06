"""
主力缩量信号 (vol_signal / buy_A) v1.0
────────────────────────────────────────────────────────────
来源：抖音「金融街小龙女」操盘手方法论的全市场实证（2026-09-25）
  · 认知内核：**真拉升静悄悄** —— 大阳线 + 缩量 = 无抛压 / 主力控盘
  · 与散户直觉完全相反（散户追"放量大阳线"）

信号定义（buy_A）：
    当日涨幅 > 5%  AND  量比 < 1.0  AND  距20日高 > -5%

全市场实证（hunter-v2/data/factor_panel.db，1,766,923 行 / 5,544 只 / 2025-03~2026-09）：
  ┌──────────────────────┬──────────┬─────────┐
  │ 口径                 │ 次日收益 │ 胜率    │
  ├──────────────────────┼──────────┼─────────┤
  │ 全样本基准           │ +0.07%   │ 48.0%   │
  │ buy_A（成本前）      │ +2.86%   │ 63.8%   │
  │ buy_A（成本后0.35%） │ +2.51%   │ 62.3%   │
  │ 对照:放量大阳+贴高   │ +0.27%   │ 44.8%   │  ← 相差 10 倍
  └──────────────────────┴──────────┴─────────┘
  分年度：2025 +3.27%/66.6% ｜ 2026 +2.57%/62.0%
  分板块：主板 +3.08%/67.0% ｜ 创业+科创 +1.77%/49.0%（中位数为负 → 本模块默认只做主板）
  样本外：训练(25-03~26-02) +3.05%/65.2% ｜ 测试(26-03~) +1.79%/58.4%
  显著性：t=+20.25（成本后）
  中位数：+2.86%（成本后，非尾部拉高）

⚠️ 与 cascade_screen 现有逻辑的冲突（重要）：
  现有粗筛**按量比降序排序**（追活跃），本信号要**量比<1**（缩量）→ 方向相反，
  因此本模块**不接入粗筛过滤链**，而作为**独立信号源**（供策略层/人工参考）。

默认 enabled=False —— 按项目铁律「优化项必须逐项单独 A/B、默认关」，需显式开启。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("aurora.vol_signal")

# ═══════════════════════════════════════════════════════════════
# 默认配置
# ═══════════════════════════════════════════════════════════════
VOL_SIGNAL_DEFAULTS: Dict[str, Any] = {
    "enabled": False,          # 铁律：默认关
    "min_pct_chg": 5.0,        # 当日涨幅下限 %
    "max_vol_ratio": 1.0,      # 量比上限（缩量）
    "min_dist_hi": -5.0,       # 距 20 日高下限 %（越接近 0 越好）
    "main_board_only": True,   # 实证：创业板/科创胜率仅 49% 且中位数为负
    "ban_st": True,
    "ban_kcb": True,           # 688/689
    "ban_bj": True,            # 8/4/920 北交所
    "ban_new_days": 60,        # 上市不足 N 日不做（需外部提供 listed_days）
    "min_amount_yi": 1.0,      # 最小成交额(亿)，流动性下限
}


def _is_main_board(code: str) -> bool:
    """主板判定：沪 60x / 深 00x（排除 300/301/688/689/8x/4x/920）"""
    if code.startswith(("300", "301", "688", "689", "920", "8", "4")):
        return False
    return code.startswith(("60", "00"))


def compute_dist_hi(klines: List[Dict[str, Any]]) -> Optional[float]:
    """距 20 日高（%）。klines 升序，含 close/high；用最新一根之前的数据（无未来函数）"""
    if not klines or len(klines) < 21:
        return None
    prev = klines[-1]                       # T 日（当日）
    hist = klines[-21:-1]                   # T-20 .. T-1
    hi = max(float(k.get("high") or 0) for k in hist)
    pc = float(prev.get("close") or 0)
    if hi <= 0 or pc <= 0:
        return None
    # 注意：用 T-1 收盘 对 T-20..T-1 的 20 日高（与实证口径一致）
    return (float(hist[-1].get("close") or 0) / hi - 1) * 100


def scan_vol_signal(quotes: Dict[str, Dict[str, Any]],
                    get_klines: Callable[[str, int], Optional[List[Dict[str, Any]]]],
                    cfg: Optional[Dict[str, Any]] = None,
                    listed_days: Optional[Dict[str, int]] = None) -> List[Dict[str, Any]]:
    """扫描满足 buy_A 的标的。

    Args:
        quotes: {code: {name, price, pct_chg, vol_ratio, amount(元), ...}}
                —— 需含当日涨跌幅与量比（腾讯/东财快照均有）
        get_klines: callable(code, n) -> 升序 K 线 list[{close, high, ...}]，n>=21
        cfg: 覆盖 VOL_SIGNAL_DEFAULTS
        listed_days: 可选 {code: 上市天数}，用于 ban_new_days

    Returns:
        [{'code','name','pct_chg','vol_ratio','dist_hi','price','amount_yi','reason'}]
    """
    c = dict(VOL_SIGNAL_DEFAULTS)
    c.update(cfg or {})
    if not c.get("enabled", False):
        logger.info("[vol_signal] disabled, skip")
        return []

    out: List[Dict[str, Any]] = []
    for code, q in (quotes or {}).items():
        try:
            name = str(q.get("name") or "")
            if c["ban_st"] and ("ST" in name.upper()):
                continue
            if c["ban_bj"] and code.startswith(("920", "8", "4")):
                continue
            if c["ban_kcb"] and code.startswith(("688", "689")):
                continue
            if c["main_board_only"] and not _is_main_board(code):
                continue
            if listed_days and listed_days.get(code, 9999) < c["ban_new_days"]:
                continue

            pct = float(q.get("pct_chg") or 0)
            vr = float(q.get("vol_ratio") or 0)
            amt = float(q.get("amount") or 0)
            if pct < c["min_pct_chg"]:
                continue
            if vr <= 0 or vr >= c["max_vol_ratio"]:
                continue
            if amt and amt < c["min_amount_yi"] * 1e8:
                continue

            kl = get_klines(code, 25)
            dist = compute_dist_hi(kl) if kl else None
            if dist is None or dist < c["min_dist_hi"]:
                continue

            out.append({
                "code": code, "name": name,
                "pct_chg": round(pct, 2), "vol_ratio": round(vr, 2),
                "dist_hi": round(dist, 2),
                "price": float(q.get("price") or 0),
                "amount_yi": round(amt / 1e8, 2) if amt else None,
                "reason": "缩量大阳+贴20日高(主力静悄悄拉升)",
            })
        except Exception as e:
            logger.debug("[vol_signal] %s skip: %s", code, e)

    out.sort(key=lambda x: x["dist_hi"], reverse=True)   # 越贴近 20 日高越优先
    logger.info("[vol_signal] 命中 %d 只", len(out))
    return out


def score_vol_signal(pct_chg: float, vol_ratio: float, dist_hi: float,
                     cfg: Optional[Dict[str, Any]] = None) -> float:
    """连续打分版（供策略层叠加使用）：量比越低、越贴高、涨幅适度 → 分越高。"""
    c = dict(VOL_SIGNAL_DEFAULTS)
    c.update(cfg or {})
    if vol_ratio <= 0 or vol_ratio >= c["max_vol_ratio"]:
        return 0.0
    if pct_chg < c["min_pct_chg"] or dist_hi < c["min_dist_hi"]:
        return 0.0
    import math
    s_vol = -math.log(max(vol_ratio, 0.05))          # 量比越低越高
    s_pos = max(0.0, 1.0 - abs(dist_hi) / 10.0)      # 越贴 20 日高越高
    s_chg = min(1.0, (pct_chg - c["min_pct_chg"]) / 5.0)
    return round(max(0.0, s_vol) * 0.5 + s_pos * 0.3 + s_chg * 0.2, 4)
