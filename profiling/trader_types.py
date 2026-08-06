"""交易员类型定义 — 6种风格 × 15个配置维度"""

TRADER_PROFILES = {
    "上班族中短线": {
        "code": "office_swing",
        "holding_period": "3-10天",
        "risk_tolerance": "稳健(<10%)",
        "screen_time": "早+晚(30min)",
        "analysis_style": "技术面为主",
        "trader_level": "中级",
        "primary_kline": "daily",
        "secondary_kline": "60min",
        "min_kline_days": 120,
        "strategy_weights": {"momentum_breakout": 2.0, "sector_rotation": 0.5, "wave_point": 0.5, "mean_reversion": 0.0},
        "risk": {"stop_loss_pct": 0.05, "take_profit_pct": 0.10, "max_position_pct": 0.20, "max_positions": 5, "daily_loss_limit_pct": -3.0, "kelly_fraction": 0.5, "trailing_stop_activation": 0.05, "trailing_stop_distance": 0.03},
        "market": {"min_score_to_trade": 40, "min_score_to_full": 65, "bear_regime_stop": True},
        "coach_style": "温和省时", "push_frequency": "早+晚两次", "training_focus": ["止损执行", "仓位管理"],
        "description": "适合朝九晚五的上班族，日线级别波段操作，低维护成本",
    },
    "短线狙击手": {
        "code": "short_sniper", "holding_period": "1-3天", "risk_tolerance": "进取(<18%)", "screen_time": "全职(8h)", "analysis_style": "技术面+板块共振", "trader_level": "高级",
        "primary_kline": "60min", "secondary_kline": "15min", "min_kline_days": 60,
        "strategy_weights": {"momentum_breakout": 2.5, "sector_rotation": 1.5, "wave_point": 0.5, "mean_reversion": 0.0},
        "risk": {"stop_loss_pct": 0.04, "take_profit_pct": 0.08, "max_position_pct": 0.28, "max_positions": 7, "daily_loss_limit_pct": -5.0, "kelly_fraction": 0.75, "trailing_stop_activation": 0.04, "trailing_stop_distance": 0.025},
        "market": {"min_score_to_trade": 30, "min_score_to_full": 55, "bear_regime_stop": False},
        "coach_style": "果断冷静", "push_frequency": "实时推送", "training_focus": ["情绪管理", "信息甄别"],
        "description": "全职短线狙击手 — 合并原全职短线客(技术突破)+消息面短线(板块事件驱动)的双驱动风格，1-3天快进快出",
    },
    "趋势跟踪者": {
        "code": "trend_follower", "holding_period": "10-30天", "risk_tolerance": "稳健(<10%)", "screen_time": "半职(2-4h)", "analysis_style": "技术面+宏观", "trader_level": "中级",
        "primary_kline": "daily", "secondary_kline": "weekly", "min_kline_days": 250,
        "strategy_weights": {"momentum_breakout": 2.0, "wave_point": 1.0, "sector_rotation": 0.5, "mean_reversion": 0.0},
        "risk": {"stop_loss_pct": 0.07, "take_profit_pct": 0.18, "max_position_pct": 0.20, "max_positions": 4, "daily_loss_limit_pct": -3.0, "kelly_fraction": 0.6, "trailing_stop_activation": 0.08, "trailing_stop_distance": 0.05},
        "market": {"min_score_to_trade": 45, "min_score_to_full": 70, "bear_regime_stop": True},
        "coach_style": "沉稳大局", "push_frequency": "每日晨报", "training_focus": ["仓位管理", "趋势识别"],
        "description": "追随大趋势的波段交易者，日线+周线级别，持仓周期10-30天",
    },
    "新手入门": {
        "code": "beginner", "holding_period": "3-10天", "risk_tolerance": "保守(<5%)", "screen_time": "收盘后", "analysis_style": "按系统信号", "trader_level": "新手",
        "primary_kline": "daily", "secondary_kline": "daily", "min_kline_days": 120,
        "strategy_weights": {"momentum_breakout": 1.0, "wave_point": 1.0, "sector_rotation": 0.0, "mean_reversion": 0.0},
        "risk": {"stop_loss_pct": 0.03, "take_profit_pct": 0.06, "max_position_pct": 0.10, "max_positions": 3, "daily_loss_limit_pct": -2.0, "kelly_fraction": 0.25, "trailing_stop_activation": 0.03, "trailing_stop_distance": 0.02},
        "market": {"min_score_to_trade": 50, "min_score_to_full": 75, "bear_regime_stop": True},
        "coach_style": "耐心教学", "push_frequency": "按需推送", "training_focus": ["系统一致性", "止损习惯"],
        "description": "刚入门的交易者，保守的均值回归策略，小仓位练习系统执行",
    },
    "价值投资者": {
        "code": "value_investor", "holding_period": "30天+", "risk_tolerance": "保守(<5%)", "screen_time": "佛系(周看一次)", "analysis_style": "基本面+估值", "trader_level": "高级",
        "primary_kline": "weekly", "secondary_kline": "daily", "min_kline_days": 500,
        "strategy_weights": {"momentum_breakout": 1.5, "mean_reversion": 0.5, "wave_point": 0.5, "sector_rotation": 0.0},
        "risk": {"stop_loss_pct": 0.10, "take_profit_pct": 0.25, "max_position_pct": 0.25, "max_positions": 3, "daily_loss_limit_pct": -5.0, "kelly_fraction": 0.4, "trailing_stop_activation": 0.10, "trailing_stop_distance": 0.06},
        "market": {"min_score_to_trade": 30, "min_score_to_full": 55, "bear_regime_stop": False},
        "coach_style": "理性数据", "push_frequency": "每周简报", "training_focus": ["基本面分析", "耐心持有"],
        "description": "深度价值投资者，周线级别决策，长期持有优质资产，不受短期波动干扰",
    },
}


# ── 分类施策: 6Agent差异化选股参数 ──
SCREENING_CONFIGS = {
    "上班族中短线": {
        "pool": "蓝筹+中大盘",
        "desc": "日线波段,大市值蓝筹,均线突破+缠论三买",
        "max_price": 200,
        "min_mcap_yi": 50,
        "max_mcap_yi": 20000,
        "min_turnover": 0.3,
        "min_pe": -100,
        "max_pe": 500,
        "min_vol_ratio": 0.5,
        "signal_prefer": {"momentum_breakout": 2.0, "wave_point": 1.5, "sector_rotation": 0.5, "chan_buy3": 0.5, "123_rule": 0.5, "first_board": 0.0},
    },
    "短线狙击手": {
        "pool": "中小盘+涨停板+热点板块",
        "desc": "1-3天超短,技术突破+板块共振,激进",
        "max_price": 300,
        "min_mcap_yi": 20,
        "max_mcap_yi": 8000,
        "min_turnover": 0.5,
        "min_pe": -200,
        "max_pe": 1500,
        "min_vol_ratio": 0.8,
        "signal_prefer": {"momentum_breakout": 2.5, "first_board": 2.0, "sector_rotation": 2.0, "naked_pinbar": 1.5, "naked_engulf": 1.0, "williams_r": 1.5, "orb": 1.0, "pullback": 1.0},
    },
    "趋势跟踪者": {
        "pool": "大盘趋势+周线多头",
        "desc": "10-30天趋势跟踪,周线定方向",
        "max_price": 500,
        "min_mcap_yi": 100,
        "max_mcap_yi": 50000,
        "min_turnover": 0.1,
        "min_pe": 0,
        "max_pe": 200,
        "min_vol_ratio": 0.3,
        "signal_prefer": {"momentum_breakout": 2.0, "ma_breakout": 1.5, "wave_point": 1.5, "chan_buy1": 1.0, "chan_buy3": 1.0},
    },
    "新手入门": {
        "pool": "大市值+低波动",
        "desc": "3-10天保守,大市值PE<100,小仓位",
        "max_price": 100,
        "min_mcap_yi": 100,
        "max_mcap_yi": 20000,
        "min_turnover": 0.1,
        "min_pe": 0,
        "max_pe": 100,
        "min_vol_ratio": 0.3,
        "signal_prefer": {"momentum_breakout": 1.0, "wave_point": 1.0, "mean_reversion": 0.5, "sector_rotation": 0.0},
    },
    "价值投资者": {
        "pool": "沪深300+低PE+高ROE",
        "desc": "30天+长期持有,低PE(5-30)+大市值",
        "max_price": 1000,
        "min_mcap_yi": 200,
        "max_mcap_yi": 50000,
        "min_turnover": 0.05,
        "min_pe": 5,
        "max_pe": 30,
        "min_vol_ratio": 0.1,
        "signal_prefer": {"momentum_breakout": 1.5, "mean_reversion": 0.5, "ma_breakout": 0.5, "wave_point": 0.5, "sector_rotation": 0.0},
    },
}

def get_screening_config(name="上班族中短线"):
    return SCREENING_CONFIGS.get(name, SCREENING_CONFIGS["上班族中短线"])

def get_trader_profile(name="上班族中短线"):
    return TRADER_PROFILES.get(name, TRADER_PROFILES["上班族中短线"])

def list_profiles():
    return list(TRADER_PROFILES.keys())

def detect_profile_from_answers(answers):
    scores = {name: 0 for name in TRADER_PROFILES}
    holding_map = {"A": "短线狙击手", "B": "上班族中短线", "C": "趋势跟踪者", "D": "价值投资者", "E": "价值投资者"}
    if answers.get("q1") in holding_map:
        scores[holding_map[answers["q1"]]] += 25
    risk_map = {"A": "新手入门", "B": "上班族中短线", "C": "短线狙击手", "D": "短线狙击手"}
    if answers.get("q2") in risk_map:
        scores[risk_map[answers["q2"]]] += 25
    time_map = {"A": "短线狙击手", "B": "趋势跟踪者", "C": "上班族中短线", "D": "价值投资者"}
    if answers.get("q3") in time_map:
        scores[time_map[answers["q3"]]] += 25
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "上班族中短线"