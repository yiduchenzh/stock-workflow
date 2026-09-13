# -*- coding: utf-8 -*-
"""昨收战法最优参数（BEST_PARAMS 终态, 2026-08-09）— 与 web 工程 hunter-v2 完全一致。

来源: hunter-v2/backend/limitup_backtest.py BEST_PARAMS（2026-08-08~09 网格搜索+多票A/B验证）。
best_params.json（evolve.py 进化引擎产物）优先覆盖代码默认值。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

# ⭐ 网格搜索最优参数（2026-08-08, 宝鼎432组合+4只验证全提升）:
# hold_min=5(25分钟有效,更稳) / t0_gap=4.0(高开更严) / t0_amp=1.5 / t0_drop=0.3 / add_vol=1.0
# ⭐ 2026-08-08 优化7 加减仓: 加仓②(连续3根站稳昨收+放量)开 + 减仓逐根扫描 → 平均75.2%→80.1%(+4.9pp)
# ⭐ 2026-08-09 优化:
#   ✅ add_intraday=True 盘中加仓（P1-1）: 加仓价从尾盘15:00改盘中触发K收盘 → 强势池4票全升
#   ❌ t0_add_mutex 放弃（P0-1 伪优化）: 把合理加仓也禁了(73→14次), 收益-3.4pp——以回测为准
#   ✅ stop_single_pct=9.0 保留（P2 安全网）: 防尾部风险不伤收益
#   ✅ trend_layers=True 趋势分层（优化12）: 上升8成/震荡5成/下降3成 + 下降禁加仓/禁弱转强低吸
#   ✅ trend_clear_confirm=True: 上升趋势破位清仓需收盘<昨日MA10（防过早卖出）——战法命门, 关掉-95pp
#   ✅ t0_roll_trend=True + t0_up_ratio=0.35 底仓滚动（优化13）: up35%/range30%/down15%
#   ⚠️ absorb_up_only/absorb_hold/absorb_vol 低吸门禁 A/B 验证全部伤害单票 → 默认关（前端标注替代）
BEST_PARAMS: Dict[str, Any] = {
    "hold_min": 5, "t0_gap_pct": 4.0, "t0_amp_pct": 1.5, "t0_drop_ratio": 0.3, "add_vol": 1.0,
    "add_break": True, "reduce_upper": 1.5,
    "add_intraday": True, "stop_single_pct": 9.0,
    "trend_layers": True, "trend_clear_confirm": True,
    "t0_roll_trend": True, "t0_up_ratio": 0.35,
    # ⭐ 2026-08-10 P1 优化: 建仓量能确认（开盘3根累计量>前5日均量）— 5票A/B +41.7pp 唯一正贡献
    # 与 web limitup_backtest.BEST_PARAMS 同步
    "entry_vol_confirm": 1.0,
}


def load_best_params() -> Dict[str, Any]:
    """BEST_PARAMS + best_params.json 覆盖（evolve.py 进化引擎产物优先）。"""
    params = dict(BEST_PARAMS)
    try:
        _bp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "best_params.json")
        if os.path.exists(_bp_path):
            with open(_bp_path, encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict) and saved:
                params = {**params, **saved}
    except Exception:
        pass
    return params
