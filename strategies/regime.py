"""市场状态策略映射 — 牛熊不同战法"""
import logging
logger = logging.getLogger("aurora.regime")

# ───── 牛熊战法配置 ─────
REGIME_CONFIG = {
    "bull_strong": {
        "策略": "满仓进攻",
        "交易原则": "顺势而为,持股为主,回调加仓",
        "active_strategies": ["momentum_breakout", "sector_rotation", "wave_point", "chan_", "naked_"],
        "战法侧重": "只做最强:突破+强势龙头", 
        "params": {}, "max_positions": 5, "kelly_mult": 1.0,
        "stop_loss_pct": 0.05, "take_profit_pct": 0.12,
        "confirmation_threshold": 55,  # 低门槛,更多信号
        "min_score_to_trade": 30,
        "可加入日K线": 60,
    },
    "bull_weak": {
        "策略": "谨慎做多",
        "交易原则": "选强势板块强势股,降低仓位,严格止损",
        "active_strategies": ["momentum_breakout", "sector_rotation", "chan_", "naked_"],
        "战法侧重": "仅强势股突破",
        "params": {}, "max_positions": 3, "kelly_mult": 0.7,
        "stop_loss_pct": 0.04, "take_profit_pct": 0.08,
        "confirmation_threshold": 60,
        "min_score_to_trade": 40,
    },
    "range": {
        "策略": "高抛低吸",
        "交易原则": "不追涨不杀跌,支撑买压力卖,快进快出",
        "active_strategies": ["momentum_breakout", "wave_point", "chan_", "naked_"],
        "战法侧重": "强势股回调低吸+突破追涨",
        "params": {}, "max_positions": 2, "kelly_mult": 0.5,
        "stop_loss_pct": 0.03, "take_profit_pct": 0.06,
        "confirmation_threshold": 65,  # 高门槛,只做最确定的信号
        "min_score_to_trade": 50,
    },
    "bear_weak": {
        "策略": "防守反击",
        "交易原则": "熊市轻仓,仅逆势强势股",
        "active_strategies": ["momentum_breakout", "chan_", "naked_"],
        "战法侧重": "仅逆势强势股",
        "params": {}, "max_positions": 1, "kelly_mult": 0.25,
        "stop_loss_pct": 0.02, "take_profit_pct": 0.04,
        "confirmation_threshold": 75,  # 极严格
        "min_score_to_trade": 60,
    },
    "bear_strong": {
        "策略": "极轻仓观望",
        "交易原则": "仅最强逆势股,涨>5%+量比>3才考虑,严止损快跑",
        "active_strategies": ["momentum_breakout", "chan_", "naked_"],
        "战法侧重": "仅逆势强势股",
        "params": {}, "max_positions": 1, "kelly_mult": 0.15,
        "stop_loss_pct": 0.015, "take_profit_pct": 0.03,
        "confirmation_threshold": 80,
        "min_score_to_trade": 70,  # 永不交易
    },
}

def get_regime_config(regime):
    return REGIME_CONFIG.get(regime, REGIME_CONFIG["range"])

def filter_strategies_by_regime(regime, strategies):
    active = get_regime_config(regime)["active_strategies"]
    result = []
    for s in strategies:
        if not s:
            continue
        for a in active:
            if a.endswith("_"):  # 前缀匹配: chan_ / naked_
                if s.startswith(a):
                    result.append(s)
                    break
            else:
                if s == a:
                    result.append(s)
                    break
    return result

# ── P0升级: Regime感知选股策略 ──
# 不同市场状态应该偏好不同的信号类型
# bear_weak下: 超跌反弹+逆势抗跌 > 动量突破
# bull_strong下: 动量突破+趋势延续 > 超跌反弹
REGIME_SCREENING_STRATEGY = {
    "bull_strong": {
        "prefer_signals": ["momentum_breakout", "first_board", "ma_breakout", "chan_buy3", "naked_engulf"],
        "avoid_signals": ["mean_reversion", "chan_buy1"],
        # 2026-07-31优化: 牛市放宽阈值(原0.5/0.8全市场最严导致踏空)
        # 牛市行情应提高参与度, 放量确认但不过滤
        "min_turnover": 0.2,
        "min_vol_ratio": 0.4,
        "bearish_filter": False,   # 不额外过滤
        "bearish_confirm_msgs": [],  # 不需要确认信息
    },
    "bull_weak": {
        "prefer_signals": ["momentum_breakout", "sector_rotation", "chan_buy2", "chan_buy3", "wave_point"],
        "avoid_signals": ["mean_reversion", "first_board"],
        "min_turnover": 0.25,
        "min_vol_ratio": 0.4,
        "bearish_filter": False,
        "bearish_confirm_msgs": [],
    },
    "range": {
        "prefer_signals": ["naked_pinbar", "naked_supply_demand", "wave_point", "chan_buy2", "mean_reversion"],
        "avoid_signals": ["first_board", "momentum_breakout"],
        "min_turnover": 0.3,
        "min_vol_ratio": 0.5,
        "bearish_filter": False,
        "bearish_confirm_msgs": [],
    },
    "bear_weak": {
        "prefer_signals": ["chan_buy1", "naked_pinbar", "naked_supply_demand", "mean_reversion", "sector_rotation"],
        "avoid_signals": ["first_board", "momentum_breakout", "ma_breakout"],
        "min_turnover": 0.1,       # 熊市放低换手门槛
        "min_vol_ratio": 0.2,      # 熊市放低量比门槛
        "bearish_filter": True,    # 熊市额外过滤: 排除大盘下跌时也跟跌的股
        "bearish_confirm_msgs": ["确认逆势抗跌", "缩量横盘在均线上"],
    },
    "bear_strong": {
        "prefer_signals": ["chan_buy1", "naked_pinbar"],
        "avoid_signals": ["momentum_breakout", "first_board", "sector_rotation", "ma_breakout", "wave_point"],
        "min_turnover": 0.05,
        "min_vol_ratio": 0.1,
        "bearish_filter": True,
        "bearish_confirm_msgs": ["确认超跌反弹", "大盘企稳信号"],
    },
}

# ── P0升级: 6Agent差异化交易风格 ──
# 每个Agent在持仓管理、监控频率、止损风格上各有不同
AGENT_TRADING_STYLES = {
    "上班族中短线": {
        "monitor_interval": 30,         # 每30分钟检查持仓
        "trend_health_threshold": 40,   # 健康度<40才减仓(较宽松)
        "exit_style": "gradual",        # 逐步退出
        "max_hold_days": 10,            # 最长持仓10天
        "trailing_activation": 0.05,    # 盈利5%启动移动止盈
        "stop_loss_pct": 0.05,          # 5%硬止损
        "take_profit_pct": 0.10,        # 10%止盈
        "bear_allow_trade": True,       # 熊市允许交易
        "bear_max_positions": 2,        # 熊市最多2只
    },
    "全职短线客": {
        "monitor_interval": 10,         # 每10分钟检查持仓(高频)
        "trend_health_threshold": 60,   # 健康度<60即减仓(敏感)
        "exit_style": "aggressive",     # 激进退出
        "max_hold_days": 3,             # 最长持仓3天
        "trailing_activation": 0.03,    # 盈利3%启动移动止盈
        "stop_loss_pct": 0.03,          # 3%硬止损
        "take_profit_pct": 0.06,        # 6%止盈
        "bear_allow_trade": True,       # 熊市允许交易(做超短反弹)
        "bear_max_positions": 1,        # 熊市最多1只
    },
    "趋势跟踪者": {
        "monitor_interval": 60,         # 每60分钟检查(低频)
        "trend_health_threshold": 30,   # 健康度<30才关注(极宽松)
        "exit_style": "trend_confirmed", # 趋势确认反转才退出
        "max_hold_days": 30,            # 最长持仓30天
        "trailing_activation": 0.08,    # 盈利8%启动
        "stop_loss_pct": 0.07,          # 7%宽止损
        "take_profit_pct": 0.18,        # 18%止盈
        "bear_allow_trade": False,      # 熊市不交易
        "bear_max_positions": 0,
    },
    "新手入门": {
        "monitor_interval": 60,         # 每60分钟检查
        "trend_health_threshold": 50,   # 健康度<50减仓
        "exit_style": "conservative",   # 保守退出
        "max_hold_days": 10,
        "trailing_activation": 0.03,
        "stop_loss_pct": 0.03,          # 3%硬止损(严)
        "take_profit_pct": 0.06,        # 6%止盈(小)
        "bear_allow_trade": False,      # 熊市不交易
        "bear_max_positions": 0,
    },
    "消息面短线": {
        "monitor_interval": 15,         # 每15分钟检查
        "trend_health_threshold": 50,
        "exit_style": "news_driven",    # 消息驱动退出
        "max_hold_days": 3,
        "trailing_activation": 0.05,
        "stop_loss_pct": 0.05,
        "take_profit_pct": 0.10,
        "bear_allow_trade": False,      # 熊市消息股退潮快，不交易
        "bear_max_positions": 0,
    },
    "价值投资者": {
        "monitor_interval": 120,        # 每120分钟(佛系)
        "trend_health_threshold": 20,   # 健康度<20才清仓(极宽松)
        "exit_style": "fundamental",    # 基本面驱动
        "max_hold_days": 60,
        "trailing_activation": 0.10,
        "stop_loss_pct": 0.10,          # 10%宽止损
        "take_profit_pct": 0.25,
        "bear_allow_trade": True,       # 熊市可以越跌越买
        "bear_max_positions": 1,
    },
}


def get_regime_screening_strategy(regime: str) -> dict:
    """获取当前regime下的选股偏好"""
    return REGIME_SCREENING_STRATEGY.get(regime, REGIME_SCREENING_STRATEGY["range"])


def get_agent_trading_style(profile_name: str) -> dict:
    """获取Agent的差异化交易风格"""
    return AGENT_TRADING_STYLES.get(profile_name, AGENT_TRADING_STYLES["上班族中短线"])


def get_trading_advice(regime: str) -> str:
    """获取当前市场状态的交易建议"""
    cfg = get_regime_config(regime)
    return f"[{cfg['策略']}] {cfg['交易原则']}"

def get_dynamic_weights(market_score, market_regime):
    """按市场状态动态调整策略权重"""
    weights = {"wave_point": 0.0, "momentum_breakout": 0.0, "mean_reversion": 0.0, "sector_rotation": 0.0}
    cfg = get_regime_config(market_regime)
    mul = cfg["kelly_mult"]
    active = cfg["active_strategies"]
    
    if "momentum_breakout" in active:
        weights["momentum_breakout"] = round(1.5 * mul, 2) if market_score >= 70 else round(1.0 * mul, 2)
    if "wave_point" in active:
        weights["wave_point"] = round(1.5 * mul, 2)
    if "mean_reversion" in active:
        weights["mean_reversion"] = round(1.5 * mul, 2)
    if "sector_rotation" in active:
        weights["sector_rotation"] = round(0.5 * mul, 2)
    
    return weights

def get_regime_params(regime: str) -> dict:
    """获取市场状态对应的风控参数"""
    cfg = get_regime_config(regime)
    return {
        "stop_loss_pct": cfg["stop_loss_pct"],
        "take_profit_pct": cfg["take_profit_pct"],
        "confirmation_threshold": cfg["confirmation_threshold"],
        "max_positions": cfg["max_positions"],
        "min_score_to_trade": cfg["min_score_to_trade"],
        "kelly_mult": cfg["kelly_mult"],
        "trading_advice": get_trading_advice(regime),
    }

def adapt_market_regime(market_score: float) -> str:
    """从market_score映射到regime(含宏观修正)"""
    if market_score >= 70: return "bull_strong"
    elif market_score >= 55: return "bull_weak"
    elif market_score >= 40: return "range"
    elif market_score >= 20: return "bear_weak"
    else: return "bear_strong"