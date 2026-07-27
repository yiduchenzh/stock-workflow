"""微结构执行增强模块 — Almgren-Chriss冲击成本/VWAP-TWAP执行/限价市价单选择

包含:
  1. AlmgrenChrissImpact  — Almgren-Chriss冲击成本模型 (永久+临时冲击)
  2. VWAPExecutionPlan    — VWAP执行计划生成器 (按历史成交量分布)
  3. TWAPExecutionPlan    — TWAP执行计划生成器 (均匀时间分割)
  4. OrderTypeSelector    — 限价单 vs 市价单智能选择
  5. MicrostructureSlippage — 增强滑点模型 (接入SimAccount管线)

所有模型均带A股校准参数 (日均成交额分层、日内时段因子)
"""
import math, logging, random
from typing import Optional
from datetime import datetime, time as dtime, timedelta

logger = logging.getLogger("aurora.microstructure")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A股日内成交量分布权重 (基于沪深300指数成分股5年统计)
# 每个时段占总成交量的比例
_INTRADAY_VOLUME_PROFILE: dict[tuple[int, int], float] = {
    ( 9, 30): 0.06,   # 9:30-9:35  开盘集合竞价后集中交易
    ( 9, 35): 0.05,   # 9:35-9:40
    ( 9, 40): 0.04,   # 9:40-9:45
    ( 9, 45): 0.035,  # 9:45-9:50
    ( 9, 50): 0.030,  # 9:50-9:55
    ( 9, 55): 0.030,  # 9:55-10:00
    (10,  0): 0.030,  # 10:00-10:05
    (10,  5): 0.028,  # 10:05-10:10
    (10, 10): 0.028,  # 10:10-10:15
    (10, 15): 0.025,  # 10:15-10:20
    (10, 20): 0.025,  # 10:20-10:25
    (10, 25): 0.025,  # 10:25-10:30
    (10, 30): 0.024,  # 10:30-10:35
    (10, 35): 0.024,  # 10:35-10:40
    (10, 40): 0.023,  # 10:40-10:45
    (10, 45): 0.023,  # 10:45-10:50
    (10, 50): 0.022,  # 10:50-10:55
    (10, 55): 0.022,  # 10:55-11:00
    (11,  0): 0.020,  # 11:00-11:05  午前清淡
    (11,  5): 0.018,  # 11:05-11:10
    (11, 10): 0.017,  # 11:10-11:15
    (11, 15): 0.016,  # 11:15-11:20
    (11, 20): 0.015,  # 11:20-11:25
    (11, 25): 0.014,  # 11:25-11:30
    # 午休 11:30-13:00
    (13,  0): 0.035,  # 13:00-13:05  午盘脉冲
    (13,  5): 0.032,  # 13:05-13:10
    (13, 10): 0.030,  # 13:10-13:15
    (13, 15): 0.028,  # 13:15-13:20
    (13, 20): 0.025,  # 13:20-13:25
    (13, 25): 0.024,  # 13:25-13:30
    (13, 30): 0.024,  # 13:30-13:35
    (13, 35): 0.024,  # 13:35-13:40
    (13, 40): 0.023,  # 13:40-13:45
    (13, 45): 0.023,  # 13:45-13:50
    (13, 50): 0.022,  # 13:50-13:55
    (13, 55): 0.022,  # 13:55-14:00
    (14,  0): 0.022,  # 14:00-14:05
    (14,  5): 0.022,  # 14:05-14:10
    (14, 10): 0.021,  # 14:10-14:15
    (14, 15): 0.021,  # 14:15-14:20
    (14, 20): 0.020,  # 14:20-14:25
    (14, 25): 0.020,  # 14:25-14:30
    (14, 30): 0.022,  # 14:30-14:35  尾盘博弈开始
    (14, 35): 0.024,  # 14:35-14:40
    (14, 40): 0.026,  # 14:40-14:45
    (14, 45): 0.030,  # 14:45-14:50  尾盘拉升
    (14, 50): 0.035,  # 14:50-14:55
    (14, 55): 0.040,  # 14:55-15:00  集合竞价前抢筹
}
# 归一化权重
_INTRADAY_TOTAL = sum(_INTRADAY_VOLUME_PROFILE.values())
_INTRADAY_VOLUME_PROFILE_NORM = {
    k: v / _INTRADAY_TOTAL for k, v in _INTRADAY_VOLUME_PROFILE.items()
}

# 时段列表 (排序)
_INTRADAY_SLOTS = sorted(_INTRADAY_VOLUME_PROFILE_NORM.keys())

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A股校准参数: 按日均成交额(元)分层的冲击成本系数
# 参考: Almgren & Chriss (2001) + A股市场微观结构实证
AC_CALIBRATION = {
    "ultra_liquid": {   # 超大盘 >100亿/日
        "turnover_threshold": 10_000_000_000,
        "eta": 0.08,     # 永久冲击系数
        "epsilon": 0.15, # 临时冲击系数
        "sigma_scale": 1.0,  # 波动率缩放
    },
    "high_liquid": {    # 大盘 20-100亿/日
        "turnover_threshold": 2_000_000_000,
        "eta": 0.15,
        "epsilon": 0.30,
        "sigma_scale": 1.0,
    },
    "mid_liquid": {     # 中盘 5-20亿/日
        "turnover_threshold": 500_000_000,
        "eta": 0.30,
        "epsilon": 0.55,
        "sigma_scale": 1.1,
    },
    "low_liquid": {     # 小盘 1-5亿/日
        "turnover_threshold": 100_000_000,
        "eta": 0.50,
        "epsilon": 0.90,
        "sigma_scale": 1.25,
    },
    "illiquid": {       # 微盘 <1亿/日
        "turnover_threshold": 0,
        "eta": 0.80,
        "epsilon": 1.50,
        "sigma_scale": 1.5,
    },
}

_AC_TIERS = sorted(
    AC_CALIBRATION.values(),
    key=lambda x: x["turnover_threshold"],
    reverse=True,
)


# ======================================================================
#  工具函数
# ======================================================================

def _calc_time_factor(dt: Optional[datetime] = None) -> float:
    """计算A股日内时段因子 (与sim_account中原有时间因子保持一致但更精细)

    返回值: 时段因子乘数 (开盘/尾盘约2.0-2.5x, 午前清淡~0.8x)
    """
    if dt is None:
        dt = datetime.now()
    t = dt.hour * 60 + dt.minute

    if 9 * 60 + 20 <= t < 9 * 60 + 30:      # 集合竞价
        return 1.5
    elif 9 * 60 + 30 <= t < 9 * 60 + 45:    # 开盘冲击
        return 2.0
    elif 9 * 60 + 45 <= t < 10 * 60:         # 开盘后活跃
        return 1.3
    elif 10 * 60 <= t < 11 * 60:             # 上午正常
        return 1.0
    elif 11 * 60 <= t < 11 * 60 + 30:        # 午前清淡
        return 0.8
    elif 13 * 60 <= t < 13 * 60 + 15:        # 午盘脉冲
        return 1.8
    elif 13 * 60 + 15 <= t < 13 * 60 + 30:  # 午盘回落
        return 1.3
    elif 13 * 60 + 30 <= t < 14 * 60:        # 下午正常
        return 1.0
    elif 14 * 60 <= t < 14 * 60 + 30:        # 尾盘博弈开始
        return 1.5
    elif 14 * 60 + 30 <= t < 15 * 60:        # 尾盘拉升
        return 2.5
    else:
        return 1.0  # 非交易时段


def _get_ac_params(avg_daily_turnover: float) -> dict:
    """根据日均成交额获取Almgren-Chriss冲击成本参数

    Args:
        avg_daily_turnover: 日均成交额(元)

    Returns:
        dict: 包含 eta, epsilon, sigma_scale 的参数字典
    """
    for tier in _AC_TIERS:
        if avg_daily_turnover >= tier["turnover_threshold"]:
            return tier
    return _AC_TIERS[-1]  # fallback


# ======================================================================
#  1. Almgren-Chriss 冲击成本模型
# ======================================================================

class AlmgrenChrissImpact:
    """Almgren-Chriss 市场冲击成本模型

    将大单拆分为N个子单, 计算:
      - 永久冲击 (信息泄露导致的价格永久性偏移)
      - 临时冲击 (流动性消耗导致的瞬时价格偏移)

    数学公式 (Almgren & Chriss 2001):
      Permanent impact:   I_p = η · σ · (X/V) · (Θ/T)^(1/4)
      Temporary impact:   I_t = ϵ · σ · (X/V)^(3/5) · sign(X)

    其中:
      X = 交易量(股), V = 日均交易量(股)
      σ = 年化波动率, η = 永久冲击系数
      Θ = 总交易时长, T = 交易时段长度
      ϵ = 临时冲击系数

    A股校准参数见 AC_CALIBRATION
    """

    def __init__(
        self,
        avg_daily_turnover: float = 5e8,
        annual_volatility: float = 0.30,
        eta: Optional[float] = None,
        epsilon: Optional[float] = None,
        sigma_scale: Optional[float] = None,
        trade_horizon_minutes: float = 30.0,
    ):
        """
        Args:
            avg_daily_turnover: 日均成交额(元), 用于自动选择参数层级
            annual_volatility: 年化波动率 (默认0.30 = 30%)
            eta: 永久冲击系数 (None=自动从层级选择)
            epsilon: 临时冲击系数 (None=自动从层级选择)
            sigma_scale: 波动率缩放因子 (None=自动从层级选择)
            trade_horizon_minutes: 交易时间窗口(分钟), 默认30分钟
        """
        params = _get_ac_params(avg_daily_turnover)
        self.eta = eta if eta is not None else params["eta"]
        self.epsilon = epsilon if epsilon is not None else params["epsilon"]
        self.sigma_scale = sigma_scale if sigma_scale is not None else params["sigma_scale"]
        self.annual_vol = annual_volatility
        self.trade_horizon = trade_horizon_minutes
        # 年化波动率转日内波动率: σ_daily = σ_annual / sqrt(242)
        self.daily_vol = self.annual_vol / math.sqrt(242)
        self._avg_daily_turnover = avg_daily_turnover

    def permanent_impact(self, shares: float, avg_price: float,
                         daily_volume_shares: float) -> float:
        """计算永久冲击 (价格比例偏移, 如0.001表示0.1%)

        I_p = η · σ_daily · (X/V)

        Args:
            shares: 交易股数
            avg_price: 交易均价
            daily_volume_shares: 日均成交量(股)

        Returns:
            float: 价格偏移比例 (正数表示买入冲击/卖出冲击幅度)
        """
        if daily_volume_shares <= 0:
            return 0.0
        x_v = shares / daily_volume_shares  # 参与率
        # 交易时长调整: 时长越短冲击越大
        horizon_adj = max(0.1, 30.0 / max(self.trade_horizon, 1.0)) ** 0.25
        return self.eta * self.daily_vol * self.sigma_scale * x_v * horizon_adj

    def temporary_impact(self, shares: float, avg_price: float,
                         daily_volume_shares: float) -> float:
        """计算临时冲击 (价格比例偏移)

        I_t = ϵ · σ_daily · (X/V)^(3/5)

        Args:
            shares: 交易股数
            avg_price: 交易均价
            daily_volume_shares: 日均成交量(股)

        Returns:
            float: 价格偏移比例
        """
        if daily_volume_shares <= 0:
            return 0.0
        x_v = shares / daily_volume_shares
        if x_v <= 0:
            return 0.0
        return self.epsilon * self.daily_vol * self.sigma_scale * (x_v ** 0.6)

    def total_impact(self, shares: float, avg_price: float,
                     daily_volume_shares: float) -> float:
        """总冲击成本 = 永久冲击 + 临时冲击

        Returns:
            float: 价格偏移比例
        """
        return (
            self.permanent_impact(shares, avg_price, daily_volume_shares)
            + self.temporary_impact(shares, avg_price, daily_volume_shares)
        )

    def impact_as_slippage(self, shares: float, avg_price: float,
                           daily_volume_shares: float,
                           is_buy: bool = True) -> dict:
        """以滑点形式返回冲击成本 (可直接用于SimAccount)

        Args:
            shares: 交易股数
            avg_price: 成交均价
            daily_volume_shares: 日均成交量(股)
            is_buy: True=买入, False=卖出

        Returns:
            dict: {
                "slippage_pct": 滑点百分比(如0.15表示0.15%),
                "permanent_pct": 永久冲击占比,
                "temporary_pct": 临时冲击占比,
                "fill_price": 预期成交价,
            }
        """
        p_impact = self.permanent_impact(shares, avg_price, daily_volume_shares)
        t_impact = self.temporary_impact(shares, avg_price, daily_volume_shares)
        total = p_impact + t_impact

        if is_buy:
            fill_price = avg_price * (1 + total)
        else:
            fill_price = avg_price * (1 - total)

        return {
            "slippage_pct": round(total * 100, 4),
            "permanent_pct": round(p_impact * 100, 4),
            "temporary_pct": round(t_impact * 100, 4),
            "fill_price": round(fill_price, 2),
        }

    def compute_participation_rate(self, shares: float,
                                    daily_volume_shares: float) -> float:
        """计算参与率 (X/V)"""
        if daily_volume_shares <= 0:
            return 0.0
        return shares / daily_volume_shares


# ======================================================================
#  2. VWAP 执行计划生成器
# ======================================================================

class VWAPExecutionPlan:
    """VWAP (Volume-Weighted Average Price) 执行计划生成器

    按A股历史成交量分布将大单拆分为多个子单, 在每个时段按比例下单,
    目标是使实际成交价格接近VWAP。

    A股日内成交量分布参考 _INTRADAY_VOLUME_PROFILE_NORM
    """

    def __init__(self, volume_profile: Optional[dict] = None):
        """
        Args:
            volume_profile: 自定义成交量分布 { (hour, min): weight, ... }
                            None=使用内置A股统计分布
        """
        self.profile = volume_profile if volume_profile is not None else _INTRADAY_VOLUME_PROFILE_NORM
        self.slots = sorted(self.profile.keys())

    def generate_plan(
        self,
        total_shares: int,
        min_slice_shares: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        noise: float = 0.0,
    ) -> list[dict]:
        """生成VWAP执行计划

        Args:
            total_shares: 总交易股数
            min_slice_shares: 每笔最小股数 (默认100)
            start_time: 计划开始时间 (默认=当前时间)
            end_time: 计划结束时间 (默认=15:00收盘)
            noise: 随机扰动系数 (0=严格按照分布, >0=加噪声)

        Returns:
            list[dict]: 每笔交易计划 [
                {
                    "time": datetime,      # 计划执行时间
                    "shares": int,          # 该时段股数
                    "weight": float,        # 该时段权重
                    "cumulative_pct": float, # 累计完成百分比
                },
                ...
            ]
        """
        if start_time is None:
            start_time = datetime.now()
        if end_time is None:
            end_time = start_time.replace(hour=15, minute=0, second=0, microsecond=0)

        # 过滤出在 [start_time, end_time] 范围内的时段
        valid_slots = []
        for h, m in self.slots:
            slot_dt = start_time.replace(hour=h, minute=m, second=0)
            if start_time <= slot_dt <= end_time:
                valid_slots.append((h, m))

        if not valid_slots:
            logger.warning("VWAP: 无有效时段, 使用均匀分布")
            # fallback: 将总量一次下单
            return [{
                "time": start_time,
                "shares": int(total_shares / 100) * 100,
                "weight": 1.0,
                "cumulative_pct": 100.0,
            }]

        raw_weights = [self.profile.get(s, 0) for s in valid_slots]

        # 可选: 加噪声
        if noise > 0:
            raw_weights = [w * (1 + random.uniform(-noise, noise)) for w in raw_weights]
            # 确保非负
            raw_weights = [max(w, 0) for w in raw_weights]

        total_weight = sum(raw_weights)
        if total_weight <= 0:
            # fallback 均匀分布
            raw_weights = [1.0] * len(valid_slots)
            total_weight = len(valid_slots)

        # 按权重分配股数
        plan = []
        allocated = 0
        for i, ((h, m), w) in enumerate(zip(valid_slots, raw_weights)):
            raw_shares = total_shares * w / total_weight
            slot_shares = int(raw_shares / min_slice_shares) * min_slice_shares
            if slot_shares < min_slice_shares and i == len(valid_slots) - 1:
                # 最后一个时段: 剩余全部
                slot_shares = int((total_shares - allocated) / min_slice_shares) * min_slice_shares
                if slot_shares < min_slice_shares:
                    slot_shares = total_shares - allocated
            allocated += slot_shares

            plan.append({
                "time": start_time.replace(hour=h, minute=m, second=0),
                "shares": slot_shares,
                "weight": round(w / total_weight, 6),
                "cumulative_pct": round(allocated / total_shares * 100, 2) if total_shares > 0 else 0,
            })

        # 修正舍入误差: 最后剩余的100股补入最后一单
        remaining = total_shares - sum(p["shares"] for p in plan)
        if remaining > 0 and plan:
            plan[-1]["shares"] += remaining
            plan[-1]["cumulative_pct"] = 100.0
        elif remaining > 0 and not plan:
            plan.append({
                "time": start_time,
                "shares": remaining,
                "weight": 1.0,
                "cumulative_pct": 100.0,
            })

        return plan

    @staticmethod
    def estimate_vwap_price(plan: list[dict], price_series: list[float]) -> float:
        """估计VWAP价格 (按计划权重加权)

        Args:
            plan: generate_plan的输出
            price_series: 各时段的预期价格列表 (长度需与plan匹配)

        Returns:
            float: VWAP估计价
        """
        if not plan or not price_series:
            return 0.0
        total = sum(p["shares"] for p in plan)
        if total <= 0:
            return 0.0
        vwap = sum(p["shares"] * pr for p, pr in zip(plan, price_series)) / total
        return round(vwap, 2)


# ======================================================================
#  3. TWAP 执行计划生成器
# ======================================================================

class TWAPExecutionPlan:
    """TWAP (Time-Weighted Average Price) 执行计划生成器

    将总交易量在指定时间窗口内均匀分割为N个子单,
    每个时间间隔下单量相同。
    """

    def __init__(self):
        self._plan: list[dict] = []

    def generate_plan(
        self,
        total_shares: int,
        num_slices: int = 10,
        min_slice_shares: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        interval_minutes: Optional[float] = None,
    ) -> list[dict]:
        """生成TWAP执行计划

        Args:
            total_shares: 总交易股数
            num_slices: 分割份数 (与interval_minutes二选一)
            min_slice_shares: 每笔最小股数
            start_time: 计划开始时间 (默认=当前时间)
            end_time: 计划结束时间
            interval_minutes: 每笔间隔分钟数 (与num_slices二选一)

        Returns:
            list[dict]: 每笔交易计划 [
                {
                    "time": datetime,
                    "shares": int,
                    "weight": float (1/num_slices),
                    "cumulative_pct": float,
                },
                ...
            ]
        """
        if start_time is None:
            start_time = datetime.now()
        if end_time is None:
            end_time = start_time.replace(hour=15, minute=0, second=0, microsecond=0)

        total_minutes = max(1, (end_time - start_time).total_seconds() / 60.0)

        if interval_minutes is not None:
            num_slices = max(1, int(total_minutes / interval_minutes))

        if num_slices < 1:
            num_slices = 1

        # 每份基础股数
        base_shares = int(total_shares / num_slices / min_slice_shares) * min_slice_shares
        if base_shares < min_slice_shares:
            base_shares = min_slice_shares

        plan = []
        allocated = 0
        for i in range(num_slices):
            if i == num_slices - 1:
                # 最后一份: 剩余全部
                slice_shares = int((total_shares - allocated) / min_slice_shares) * min_slice_shares
                if slice_shares < min_slice_shares:
                    slice_shares = total_shares - allocated
            else:
                slice_shares = base_shares

            allocated += slice_shares
            # 时间位置
            fraction = (i + 1) / max(num_slices, 1)
            offset_seconds = total_minutes * fraction * 60
            slot_time = start_time + timedelta(seconds=offset_seconds)

            plan.append({
                "time": slot_time,
                "shares": slice_shares,
                "weight": round(1.0 / max(num_slices, 1), 6),
                "cumulative_pct": round(allocated / total_shares * 100, 2) if total_shares > 0 else 0,
            })

        # 修正舍入误差
        remaining = total_shares - sum(p["shares"] for p in plan)
        if remaining > 0 and plan:
            plan[-1]["shares"] += remaining
            plan[-1]["cumulative_pct"] = 100.0
        elif remaining > 0 and not plan:
            plan.append({
                "time": start_time,
                "shares": remaining,
                "weight": 1.0,
                "cumulative_pct": 100.0,
            })

        self._plan = plan
        return plan


# ======================================================================
#  4. 限价单 vs 市价单智能选择
# ======================================================================

class OrderTypeSelector:
    """限价单(Limit) vs 市价单(Market)智能选择

    基于以下因素决策:
      - 流动性 (日均成交额分层)
      - 波动率 (当前波动率相对历史)
      - 订单规模 (参与率 X/V)
      - 时间紧迫度 (距离收盘)
      - 买卖方向 (买入/卖出对滑点敏感度不同)
      - 盘口价差代理 (无盘口数据时用流动性层估算)
    """

    # 阈值配置 (A股校准)
    LIQUIDITY_THRESHOLDS = {
        "high": 5e9,    # 50亿/日以上 → 市价单较安全
        "mid": 1e9,     # 10-50亿/日 → 视情况
        "low": 1e8,     # 1-10亿/日 → 倾向限价单
    }

    def __init__(self, config: Optional[dict] = None):
        """
        Args:
            config: {
                "volatility_threshold": float,   # 波动率阈值 (默认0.02=2%)
                "participation_threshold": float, # 参与率阈值 (默认0.05=5%)
                "urgency_threshold_minutes": float, # 紧迫度阈值分钟 (默认15)
                "spread_estimation_factor": float,  # 价差估算因子 (默认0.002=0.2%)
            }
        """
        self.config = {
            "volatility_threshold": 0.02,
            "participation_threshold": 0.05,
            "urgency_threshold_minutes": 15.0,
            "spread_estimation_factor": 0.002,
        }
        if config:
            self.config.update(config)

    def select(
        self,
        shares: int,
        avg_price: float,
        avg_daily_turnover: float,
        daily_volume_shares: float,
        current_volatility: Optional[float] = None,
        is_buy: bool = True,
        current_time: Optional[datetime] = None,
        market_hours_remaining: Optional[float] = None,
    ) -> dict:
        """智能选择最优订单类型

        Args:
            shares: 交易股数
            avg_price: 当前价格
            avg_daily_turnover: 日均成交额(元)
            daily_volume_shares: 日均成交量(股)
            current_volatility: 当前波动率(日) (None=使用默认)
            is_buy: True=买入, False=卖出
            current_time: 当前时间 (None=now)
            market_hours_remaining: 剩余交易分钟数 (None=自动计算至15:00)

        Returns:
            dict: {
                "order_type": "limit" | "market",
                "confidence": float,        # 置信度 0.0-1.0
                "factors": dict,            # 各因素得分
                "reason": str,              # 简短理由
                "limit_price": float|None,  # 如限价单, 建议限价
                "limit_offset_bps": float,  # 限价偏离(基点)
            }
        """
        if current_time is None:
            current_time = datetime.now()

        if market_hours_remaining is None:
            # A股交易时间 9:30-11:30, 13:00-15:00
            t = current_time.hour * 60 + current_time.minute
            if 9 * 60 + 30 <= t <= 11 * 60 + 30:
                remaining = (11 * 60 + 30 - t) + 120  # 下午还有2小时
            elif 13 * 60 <= t <= 15 * 60:
                remaining = 15 * 60 - t
            else:
                remaining = 0
            market_hours_remaining = remaining

        # 1. 流动性得分 (0-1, 越高越适合市价单)
        if avg_daily_turnover >= self.LIQUIDITY_THRESHOLDS["high"]:
            liquidity_score = 0.9
        elif avg_daily_turnover >= self.LIQUIDITY_THRESHOLDS["mid"]:
            liquidity_score = 0.6
        elif avg_daily_turnover >= self.LIQUIDITY_THRESHOLDS["low"]:
            liquidity_score = 0.3
        else:
            liquidity_score = 0.1

        # 2. 波动率得分 (波动率低→市价单安全; 波动率高→限价单)
        vol = current_volatility if current_volatility else self.daily_vol if hasattr(self, 'daily_vol') else 0.02
        vol_threshold = self.config["volatility_threshold"]
        if vol <= vol_threshold * 0.5:
            volatility_score = 0.7  # 低波动, 市价单安全
        elif vol <= vol_threshold:
            volatility_score = 0.5
        elif vol <= vol_threshold * 2:
            volatility_score = 0.3  # 高波动, 限价单更安全
        else:
            volatility_score = 0.1

        # 3. 订单规模/参与率得分 (参与率越高→限价单避免冲击)
        participation = shares / max(daily_volume_shares, 1)
        part_threshold = self.config["participation_threshold"]
        if participation <= part_threshold * 0.3:
            size_score = 0.8  # 小单, 可用市价
        elif participation <= part_threshold:
            size_score = 0.5
        elif participation <= part_threshold * 3:
            size_score = 0.2  # 大单, 必须限价
        else:
            size_score = 0.05

        # 4. 时间紧迫度得分 (越临近收盘越需要市价单)
        urg_threshold = self.config["urgency_threshold_minutes"]
        if market_hours_remaining <= urg_threshold * 0.3:
            urgency_score = 0.9  # 非常紧迫
        elif market_hours_remaining <= urg_threshold:
            urgency_score = 0.7
        elif market_hours_remaining <= urg_threshold * 2:
            urgency_score = 0.4
        else:
            urgency_score = 0.2

        # 5. 买卖方向 (卖出滑点更敏感→更倾向限价)
        direction_adj = 1.1 if is_buy else 0.9

        # 综合评分 (权重: 流动性0.3, 波动率0.15, 规模0.25, 紧迫度0.3)
        composite = (
            liquidity_score * 0.30
            + volatility_score * 0.15
            + size_score * 0.25
            + urgency_score * 0.30
        ) * direction_adj

        # 限价单偏移: 基于流动性估算价差
        spread_est = self.config["spread_estimation_factor"]
        if avg_daily_turnover >= self.LIQUIDITY_THRESHOLDS["high"]:
            limit_offset_bps = 2.0  # 大盘股: 2基点
        elif avg_daily_turnover >= self.LIQUIDITY_THRESHOLDS["mid"]:
            limit_offset_bps = 5.0
        elif avg_daily_turnover >= self.LIQUIDITY_THRESHOLDS["low"]:
            limit_offset_bps = 10.0
        else:
            limit_offset_bps = 20.0

        # 高波动/大单加大偏移
        if vol > vol_threshold:
            limit_offset_bps *= 1.5
        if participation > part_threshold:
            limit_offset_bps *= 1.3

        # 决策
        if composite >= 0.6:
            order_type = "market"
            confidence = composite
            reason = "流动性好/紧迫度高/订单小 → 市价单优先"
            limit_price = None
        elif composite >= 0.35:
            order_type = "market" if urgency_score > 0.6 else "limit"
            confidence = abs(composite - 0.475) * 2  # 边界附近置信度低
            reason = "条件均衡 → " + ("市价单" if order_type == "market" else "限价单")
            if order_type == "limit":
                limit_price = self._suggest_limit_price(avg_price, is_buy, limit_offset_bps)
            else:
                limit_price = None
        else:
            order_type = "limit"
            confidence = 1.0 - composite
            reason = "流动性差/波动高/大单 → 限价单优先"
            limit_price = self._suggest_limit_price(avg_price, is_buy, limit_offset_bps)

        return {
            "order_type": order_type,
            "confidence": round(confidence, 4),
            "factors": {
                "liquidity_score": round(liquidity_score, 3),
                "volatility_score": round(volatility_score, 3),
                "size_score": round(size_score, 3),
                "urgency_score": round(urgency_score, 3),
                "direction_adj": round(direction_adj, 3),
                "participation": round(participation, 6),
                "volatility": round(vol, 6),
                "market_hours_remaining": round(market_hours_remaining, 1),
            },
            "reason": reason,
            "limit_price": round(limit_price, 2) if limit_price is not None else None,
            "limit_offset_bps": round(limit_offset_bps, 1),
        }

    @staticmethod
    def _suggest_limit_price(price: float, is_buy: bool, offset_bps: float) -> float:
        """建议限价单价格

        Args:
            price: 当前市价
            is_buy: 买入 (限价应≤市价)
            offset_bps: 偏移基点

        Returns:
            float: 建议限价
        """
        offset = offset_bps / 10000.0
        if is_buy:
            # 买入限价 ≤ 市价 (低挂)
            limit = price * (1 - offset)
        else:
            # 卖出限价 ≥ 市价 (高挂)
            limit = price * (1 + offset)
        return limit


# ======================================================================
#  5. 增强滑点模型 — 接入SimAccount管线
# ======================================================================

class MicrostructureSlippage:
    """增强滑点模型 — 替换SimAccount的固定滑点计算

    集成:
      - Almgren-Chriss冲击成本模型 (大单冲击)
      - 日内时段因子 (开盘/尾盘波动放大)
      - 流动性分层 (按日均成交额)
      - 随机噪声 (模拟微观结构噪声)
      - 限价单/市价单选择建议

    可直接被SimAccount的buy/sell方法调用, 替代原有滑点计算逻辑。
    """

    def __init__(
        self,
        avg_daily_turnover: float = 5e8,
        daily_volume_shares: float = 5_000_000,
        annual_volatility: float = 0.30,
        use_ac_model: bool = True,
    ):
        """
        Args:
            avg_daily_turnover: 日均成交额(元), 用于分层
            daily_volume_shares: 日均成交量(股)
            annual_volatility: 年化波动率
            use_ac_model: 是否使用Almgren-Chriss模型 (False=回退到简单分层滑点)
        """
        self._avg_daily_turnover = avg_daily_turnover
        self._daily_volume_shares = daily_volume_shares
        self._annual_vol = annual_volatility
        self._use_ac = use_ac_model

        # 子模型
        self.ac = AlmgrenChrissImpact(
            avg_daily_turnover=avg_daily_turnover,
            annual_volatility=annual_volatility,
        )
        self.selector = OrderTypeSelector()

        # 基础滑点分层 (与sim_account兼容)
        self.base_slippage_tiers = {
            500: 0.001,   # >500亿: 0.1%
            100: 0.002,   # 100-500亿: 0.2%
            0:   0.003,   # <100亿: 0.3%
        }

    def compute_slippage(
        self,
        shares: int,
        price: float,
        is_buy: bool = True,
        current_time: Optional[datetime] = None,
        mcap_hundred_million: float = 200.0,
        use_ac: Optional[bool] = None,
    ) -> dict:
        """计算增强滑点 — 供SimAccount买入/卖出调用

        Args:
            shares: 交易股数
            price: 参考价格
            is_buy: 买入或卖出
            current_time: 当前时间 (None=now)
            mcap_hundred_million: 市值(亿), 用于基础分层
            use_ac: 是否使用AC模型 (None=使用self._use_ac)

        Returns:
            dict: {
                "slippage": float,         # 滑点比例 (如0.0015=0.15%)
                "base_slippage": float,    # 基础分层滑点
                "time_factor": float,      # 时段因子
                "ac_impact": float,        # AC模型冲击
                "noise": float,            # 随机噪声
                "fill_price": float,       # 预期成交价
                "impact_detail": dict,     # AC模型详情 (如使用)
                "order_type_advice": dict, # 订单类型建议
            }
        """
        _use_ac = use_ac if use_ac is not None else self._use_ac
        if current_time is None:
            current_time = datetime.now()

        # 1. 基础分层滑点
        base_slip = 0.003
        for threshold, slip in sorted(self.base_slippage_tiers.items(), reverse=True):
            if mcap_hundred_million >= threshold:
                base_slip = slip
                break

        # 2. 日内时段因子
        time_factor = _calc_time_factor(current_time)

        # 3. Almgren-Chriss冲击
        ac_impact = 0.0
        impact_detail = {}
        if _use_ac:
            result = self.ac.impact_as_slippage(
                shares=shares,
                avg_price=price,
                daily_volume_shares=self._daily_volume_shares,
                is_buy=is_buy,
            )
            ac_impact = result["slippage_pct"] / 100.0  # 转小数
            impact_detail = result

        # 4. 随机噪声 (模拟微观结构噪声 ~0-0.05%)
        noise = random.uniform(0, 0.0005)

        # 5. 合成滑点
        if _use_ac and ac_impact > 0:
            # AC模型给出绝对冲击, 取代基础分层
            total_slippage = ac_impact * time_factor + noise
        else:
            # 回退: 基础分层 * 时段因子 + 噪声
            total_slippage = base_slip * time_factor + noise

        # 确保最小值
        total_slippage = max(total_slippage, 0.0003)

        # 成交价
        if is_buy:
            fill_price = price * (1 + total_slippage)
        else:
            fill_price = price * (1 - total_slippage)

        # 订单类型建议
        order_advice = self.selector.select(
            shares=shares,
            avg_price=price,
            avg_daily_turnover=self._avg_daily_turnover,
            daily_volume_shares=self._daily_volume_shares,
            current_volatility=self._annual_vol / math.sqrt(242),
            is_buy=is_buy,
            current_time=current_time,
        )

        return {
            "slippage": round(total_slippage, 6),
            "base_slippage": round(base_slip, 6),
            "time_factor": round(time_factor, 4),
            "ac_impact": round(ac_impact, 6),
            "noise": round(noise, 6),
            "fill_price": round(fill_price, 2),
            "impact_detail": impact_detail,
            "order_type_advice": order_advice,
        }

    def update_market_params(
        self,
        avg_daily_turnover: Optional[float] = None,
        daily_volume_shares: Optional[float] = None,
        annual_volatility: Optional[float] = None,
    ):
        """更新市场参数 (可用于盘中动态调整)"""
        if avg_daily_turnover is not None:
            self._avg_daily_turnover = avg_daily_turnover
            self.ac._avg_daily_turnover = avg_daily_turnover
            params = _get_ac_params(avg_daily_turnover)
            self.ac.eta = params["eta"]
            self.ac.epsilon = params["epsilon"]
            self.ac.sigma_scale = params["sigma_scale"]
        if daily_volume_shares is not None:
            self._daily_volume_shares = daily_volume_shares
        if annual_volatility is not None:
            self._annual_vol = annual_volatility
            self.ac.annual_vol = annual_volatility
            self.ac.daily_vol = annual_volatility / math.sqrt(242)


# ======================================================================
#  快捷入口
# ======================================================================

def create_microstructure(
    avg_daily_turnover: float = 5e8,
    daily_volume_shares: float = 5_000_000,
    annual_volatility: float = 0.30,
) -> MicrostructureSlippage:
    """创建微结构增强滑点模型 (快捷工厂方法)

    Args:
        avg_daily_turnover: 日均成交额(元)
        daily_volume_shares: 日均成交量(股)
        annual_volatility: 年化波动率

    Returns:
        MicrostructureSlippage 实例
    """
    return MicrostructureSlippage(
        avg_daily_turnover=avg_daily_turnover,
        daily_volume_shares=daily_volume_shares,
        annual_volatility=annual_volatility,
    )
