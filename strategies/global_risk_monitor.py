"""
[Soul] 全局风险监控 — 隔夜风险 + 宏观周期 + 四级风险定级
- get_overnight_risk(): 美股期货涨跌+USDCNY+隔夜综合评分
- get_macro_cycle_phase(): 信用/库存/美林时钟三周期同时判断
- get_risk_level(): normal/caution/high/danger 四级风险
- adjust_regime_by_risk(regime, risk): 根据风险降级regime
- 所有数据从腾讯API实时获取,无外部依赖
"""
import logging, urllib.request, json
from datetime import datetime

logger = logging.getLogger("aurora.soul.global_risk")

UA = "Mozilla/5.0"

# ─── 腾讯API辅助函数 ───

def _get_tencent_global(code: str) -> dict:
    """获取腾讯全球指数行情: usDJI, usIXIC, usINX, hsHSI, USDCNY等
    
    腾讯全球指数格式: 0=market,1=name,2=code,3=price,4=涨跌额,5=涨跌幅%
    返回: {price, change, change_pct} 或空dict
    """
    try:
        url = f"https://qt.gtimg.cn/q={code}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        resp = urllib.request.urlopen(req, timeout=8)
        raw = resp.read().decode("gbk", errors="replace")
        if "~" not in raw:
            logger.debug(f"[Soul] {code} 返回无数据: {raw[:100]}")
            return {}
        parts = raw.split("~")
        # 腾讯指数格式: name~code~price~change~change_pct ...
        # 不同指数字段位置略有不同,尽量兼容
        price = None
        change = None
        change_pct = None
        if len(parts) > 3:
            try:
                price = float(parts[3]) if parts[3] else 0
            except (ValueError, IndexError):
                pass
        if len(parts) > 4:
            try:
                change = float(parts[4]) if parts[4] else 0
            except (ValueError, IndexError):
                pass
        if len(parts) > 5:
            try:
                change_pct = float(parts[5]) if parts[5] else 0
            except (ValueError, IndexError):
                pass
        # 若price为0但change_pct仍可能在字段32(对A股格式)
        if (price is None or price == 0) and len(parts) > 32:
            try:
                price = float(parts[3]) if parts[3] else None
                change_pct = float(parts[32]) if parts[32] else change_pct
            except (ValueError, IndexError):
                pass
        result = {}
        if price is not None:
            result["price"] = price
        if change is not None:
            result["change"] = change
        if change_pct is not None:
            result["change_pct"] = change_pct
        logger.debug(f"[Soul] tencent_global({code}): {result}")
        return result
    except Exception as e:
        logger.warning(f"[Soul] 腾讯全球行情获取失败 {code}: {e}")
        return {}


def _get_usd_cny() -> dict:
    """获取美元/人民币汇率(USDCNY) — 腾讯API
    
    返回: {price, change_pct}
    """
    try:
        url = "https://qt.gtimg.cn/q=USDCNY"
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://finance.qq.com"})
        resp = urllib.request.urlopen(req, timeout=8)
        raw = resp.read().decode("gbk", errors="replace")
        # USDCNY格式: v_USDCNY="时间,买入,卖出,最新,涨跌额,涨跌幅%..."
        if '"' not in raw:
            return {}
        data = raw.split('"')[1]
        fields = data.split(",")
        if len(fields) < 6:
            return {}
        price = float(fields[3]) if fields[3] else 0
        # 腾讯国际指数格式: 涨跌幅在fields[32],但部分指数不返回
        change_pct = 0
        try:
            if len(fields) > 5 and fields[5]:
                change_pct = float(fields[5])
        except:
            change_pct = 0
        change_pct = 0
        return {"price": price, "change_pct": change_pct}
    except Exception as e:
        logger.warning(f"[Soul] USDCNY获取失败: {e}")
        return {}


# ─── 隔夜风险 ───

def get_overnight_risk() -> dict:
    """隔夜风险综合评估
    
    基于:
      - 美股三大指数(道琼斯/纳斯达克/标普500)实时涨跌
      - 恒生指数(亚太先行指标)
      - 人民币汇率USDCNY
    返回: {
        "score": 0-100 (0=极低风险, 100=极高风险),
        "level": "normal"/"caution"/"high"/"danger",
        "details": {各指数涨跌},
        "overnight_change_pct": 综合涨跌%
    }
    """
    result = {
        "score": 50,
        "level": "normal",
        "details": {},
        "overnight_change_pct": 0,
    }
    try:
        # 1. 美股三大指数
        us_indices = {
            "usDJI": "道琼斯",
            "usIXIC": "纳斯达克",
            "usINX": "标普500",
        }
        changes = []
        for code, name in us_indices.items():
            q = _get_tencent_global(code)
            if q and "change_pct" in q:
                result["details"][name] = round(q["change_pct"], 2)
                changes.append(q["change_pct"])
                logger.info(f"[Soul] get_overnight_risk {name}={q['change_pct']:.2f}%")
            else:
                result["details"][name] = None

        # 2. 恒生指数
        hsi = _get_tencent_global("hsHSI")
        if hsi and "change_pct" in hsi:
            result["details"]["恒生指数"] = round(hsi["change_pct"], 2)
            changes.append(hsi["change_pct"])
            logger.info(f"[Soul] get_overnight_risk 恒生指数={hsi['change_pct']:.2f}%")
        else:
            result["details"]["恒生指数"] = None

        # 3. 人民币汇率
        cny = _get_usd_cny()
        if cny:
            # USDCNY涨=人民币贬(利空A股), 跌=人民币升(利好A股)
            result["details"]["USDCNY"] = round(cny.get("price", 0), 4)
            result["details"]["USDCNY_change_pct"] = round(cny.get("change_pct", 0), 2)
            changes.append(-cny.get("change_pct", 0))  # 取反: CNY升值=正
            logger.info(f"[Soul] get_overnight_risk USDCNY={cny.get('price',0):.4f} chg={cny.get('change_pct',0):.2f}%")
        else:
            result["details"]["USDCNY"] = None

        # 计算综合评分
        valid_changes = [c for c in changes if c is not None]
        if valid_changes:
            avg_change = sum(valid_changes) / len(valid_changes)
            result["overnight_change_pct"] = round(avg_change, 2)
            # 综合涨跌 → 风险评分
            # 平均跌幅>1% => 高风险; >2% => 危险
            if avg_change < -2.0:
                result["score"] = 85
                result["level"] = "danger"
            elif avg_change < -1.0:
                result["score"] = 70
                result["level"] = "high"
            elif avg_change < -0.5:
                result["score"] = 60
                result["level"] = "caution"
            elif avg_change < 0.3:
                result["score"] = 50
                result["level"] = "normal"
            else:
                result["score"] = 35
                result["level"] = "normal"

        # 额外: 若USDCNY>7.2(人民币弱)叠加
        if cny and cny.get("price", 0) > 7.2:
            result["score"] = min(100, result["score"] + 10)
            if result["score"] >= 70:
                result["level"] = "high"

        logger.info(f"[Soul] overnight_risk: score={result['score']} level={result['level']} "
                     f"avg_chg={result['overnight_change_pct']:.2f}%")
        return result

    except Exception as e:
        logger.warning(f"[Soul] get_overnight_risk 异常: {e}")
        return result


# ─── 宏观周期 ───

def get_macro_cycle_phase() -> dict:
    """宏观周期三周期判断
    
    基于腾讯API可获取的数据,模拟:
      - 信用周期(通过美元/人民币强弱+恒生指数代理)
      - 库存周期(通过市场整体强弱代理)
      - 美林时钟(通过指数相对表现)
    
    由于腾讯API不提供社融/PMI/PPI等宏观指标,
    使用市场代理信号做合理推断。
    
    返回: {
        "credit_cycle": "宽松"/"中性"/"紧缩",
        "credit_score": 0-100,
        "inventory_cycle": "主动补库"/"被动补库"/"主动去库"/"被动去库",
        "inventory_score": 0-100,
        "merrill_clock": "复苏"/"过热"/"滞涨"/"衰退",
        "merrill_score": 0-100,
        "overall_phase": "expansion"/"slowdown"/"contraction"/"recovery",
        "details": {}
    }
    """
    result = {
        "credit_cycle": "中性",
        "credit_score": 50,
        "inventory_cycle": "被动去库",
        "inventory_score": 50,
        "merrill_clock": "复苏",
        "merrill_score": 50,
        "overall_phase": "recovery",
        "details": {},
    }
    try:
        # 收集数据
        # 1. USDCNY → 人民币强弱(信用周期代理)
        cny = _get_usd_cny()
        cny_level = 7.1  # 默认中性
        cny_trend = 0
        if cny:
            cny_level = cny.get("price", 7.1)
            cny_trend = cny.get("change_pct", 0)
            result["details"]["usd_cny"] = round(cny_level, 4)

        # 2. 恒生指数(中国经济先行指标)
        hsi = _get_tencent_global("hsHSI")
        hsi_chg = 0
        if hsi and "change_pct" in hsi:
            hsi_chg = hsi["change_pct"]
            result["details"]["hsi_chg"] = round(hsi_chg, 2)

        # 3. 美股(全球风险偏好)
        spy = _get_tencent_global("usINX")
        spy_chg = 0
        if spy and "change_pct" in spy:
            spy_chg = spy["change_pct"]
            result["details"]["sp500_chg"] = round(spy_chg, 2)

        # ─── 信用周期判断 ───
        # 人民币升值(USDCNY下降) + HSI上涨 => 信用宽松
        # 人民币贬值(USDCNY上升) + HSI下跌 => 信用紧缩
        credit_score = 50
        if cny_level < 7.0 and hsi_chg > 0.5:
            credit_score = 75
            result["credit_cycle"] = "宽松"
        elif cny_level < 7.05 and hsi_chg > 0:
            credit_score = 65
            result["credit_cycle"] = "偏宽松"
        elif cny_level > 7.2 and hsi_chg < -0.5:
            credit_score = 25
            result["credit_cycle"] = "紧缩"
        elif cny_level > 7.15 and hsi_chg < 0:
            credit_score = 35
            result["credit_cycle"] = "偏紧缩"
        else:
            result["credit_cycle"] = "中性"
            credit_score = 50
        result["credit_score"] = credit_score

        # ─── 库存周期判断 ───
        # 用市场整体强弱代理(HSI+SPY综合)
        # 主动补库: 经济上行+需求旺 => 指数涨
        # 被动补库: 经济下行+库存积压 => 指数跌
        # 主动去库: 经济下行+主动减仓 => 指数急跌
        # 被动去库: 经济底部+需求回暖 => 指数企稳
        combined = (hsi_chg * 0.5 + spy_chg * 0.5) if hsi_chg is not None and spy_chg is not None else (hsi_chg or spy_chg or 0)
        inventory_score = 50
        if combined > 1.5:
            result["inventory_cycle"] = "主动补库"
            inventory_score = 75
        elif combined > 0.5:
            result["inventory_cycle"] = "被动去库"
            inventory_score = 65
        elif combined < -1.5:
            result["inventory_cycle"] = "主动去库"
            inventory_score = 25
        elif combined < -0.3:
            result["inventory_cycle"] = "被动补库"
            inventory_score = 35
        else:
            result["inventory_cycle"] = "被动去库"
            inventory_score = 50
        result["inventory_score"] = inventory_score

        # ─── 美林时钟判断 ───
        # 基于: 经济增长(HSI) vs 通胀预期(USDCNY→人民币强弱代理)
        # CNY强=通缩或经济强(需结合HSI)
        if hsi_chg > 0.5 and cny_level < 7.05:
            result["merrill_clock"] = "复苏"
            result["merrill_score"] = 70
        elif hsi_chg > 0.5 and cny_level >= 7.05:
            result["merrill_clock"] = "过热"
            result["merrill_score"] = 65
        elif hsi_chg <= 0.5 and cny_level >= 7.1:
            result["merrill_clock"] = "滞涨"
            result["merrill_score"] = 35
        else:
            result["merrill_clock"] = "衰退"
            result["merrill_score"] = 40

        # ─── 综合周期阶段 ───
        avg_score = (credit_score + inventory_score + result["merrill_score"]) / 3
        if avg_score >= 60:
            result["overall_phase"] = "expansion"  # 扩张
        elif avg_score >= 45:
            result["overall_phase"] = "recovery"   # 复苏
        elif avg_score >= 35:
            result["overall_phase"] = "slowdown"   # 放缓
        else:
            result["overall_phase"] = "contraction"  # 收缩

        logger.info(f"[Soul] macro_cycle: credit={result['credit_cycle']} "
                     f"inventory={result['inventory_cycle']} "
                     f"merrill={result['merrill_clock']} "
                     f"phase={result['overall_phase']}")
        return result

    except Exception as e:
        logger.warning(f"[Soul] get_macro_cycle_phase 异常: {e}")
        return result


# ─── 风险定级 ───

def get_risk_level(overnight_score: float = None, macro_phase: str = None) -> str:
    """四级风险定级
    
    Args:
        overnight_score: 隔夜风险评分(0-100), None则实时获取
        macro_phase: 宏观周期阶段, None则实时获取
    
    Returns:
        "normal"/"caution"/"high"/"danger"
    """
    try:
        if overnight_score is None:
            overnight = get_overnight_risk()
            overnight_score = overnight.get("score", 50)

        if macro_phase is None:
            macro = get_macro_cycle_phase()
            macro_phase = macro.get("overall_phase", "recovery")

        # 宏观周期风险映射
        phase_risk = {
            "expansion": 30,
            "recovery": 40,
            "slowdown": 60,
            "contraction": 75,
        }
        phase_score = phase_risk.get(macro_phase, 50)

        # 综合: 隔夜风险(60%) + 宏观周期风险(40%)
        combined = overnight_score * 0.6 + phase_score * 0.4

        if combined >= 80:
            level = "danger"
        elif combined >= 65:
            level = "high"
        elif combined >= 50:
            level = "caution"
        else:
            level = "normal"

        logger.info(f"[Soul] risk_level: combined={combined:.1f} "
                     f"overnight={overnight_score:.0f} phase={macro_phase} "
                     f"level={level}")
        return level

    except Exception as e:
        logger.warning(f"[Soul] get_risk_level 异常: {e}")
        return "caution"


def adjust_regime_by_risk(regime: str, risk_level: str = None) -> str:
    """根据风险级别降级regime
    
    风险降级规则:
      normal: 不调整
      caution: 降一级(bull_strong→bull_weak, bull_weak→range, ...)
      high: 降两级
      danger: 强制到bear_strong
    
    Args:
        regime: 当前regime (bull_strong/bull_weak/range/bear_weak/bear_strong)
        risk_level: 风险级别, None则实时获取
    
    Returns:
        调整后的regime
    """
    try:
        if risk_level is None:
            risk_level = get_risk_level()

        if risk_level == "normal":
            return regime

        # regime等级: 0=bull_strong, 1=bull_weak, 2=range, 3=bear_weak, 4=bear_strong
        levels = ["bull_strong", "bull_weak", "range", "bear_weak", "bear_strong"]
        try:
            idx = levels.index(regime)
        except ValueError:
            idx = 2  # 未知regime默认为range

        downgrade = {"caution": 1, "high": 2, "danger": 4}.get(risk_level, 0)
        new_idx = min(idx + downgrade, 4)
        new_regime = levels[new_idx]

        if new_regime != regime:
            logger.info(f"[Soul] adjust_regime_by_risk: {regime}→{new_regime} (risk={risk_level})")

        return new_regime

    except Exception as e:
        logger.warning(f"[Soul] adjust_regime_by_risk 异常: {e}")
        return regime
