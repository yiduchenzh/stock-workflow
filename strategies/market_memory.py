"""
[Soul] 市场模式记忆库 — 记录历史K线模式+每日数据积累,匹配当前行情
- record_pattern(kline_df): 记录K线模式
- daily_snapshot(market_score, regime, top_sectors, sentiment): 每日市场状态快照
- match_current(state): 匹配历史相似周期
- 持久化: data/market_memory.json (追加模式,保留最近365天)
"""
import json, logging, numpy as np
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger("aurora.soul.market_memory")

DATA = Path(__file__).resolve().parent.parent / "data"
MEMORY_FILE = DATA / "market_memory.json"

# ─── 模式定义 ───
PATTERN_TYPES = {
    "连续阳线突破": {"特征": "连续3日阳线+成交量放大+突破前期高点", "看涨概率": 0},
    "高位放量滞涨": {"特征": "高位连续放量但涨幅收窄", "看涨概率": 0},
    "缩量阴跌": {"特征": "成交量持续萎缩+价格缓慢下跌", "看涨概率": 0},
    "V型反转": {"特征": "急跌后快速反弹+放量", "看涨概率": 0},
    "缺口回补": {"特征": "跳空缺口后在7个交易日内回补", "看涨概率": 0},
}


class MarketMemory:
    """市场模式记忆库 + 每日数据积累"""

    def __init__(self):
        self.patterns = self._load()
        logger.info(f"[Soul] market_memory loaded: {len(self.patterns)} records")

    def _load(self) -> list:
        try:
            if MEMORY_FILE.exists():
                data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
                # 兼容旧格式: if list return directly, if dict with "records" take that
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "records" in data:
                    return data["records"]
            return []
        except Exception as e:
            logger.warning(f"[Soul] market_memory加载失败: {e}")
            return []

    def _save(self):
        try:
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            old_data = {}
            try:
                if MEMORY_FILE.exists():
                    old = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
                    if isinstance(old, dict) and "daily_snapshots" in old:
                        old_data["daily_snapshots"] = old.get("daily_snapshots", [])
            except Exception:
                pass

            save_obj = {
                "records": self.patterns[-365:],
                "updated": datetime.now().isoformat(),
            }
            if old_data.get("daily_snapshots"):
                save_obj["daily_snapshots"] = old_data["daily_snapshots"]

            MEMORY_FILE.write_text(
                json.dumps(save_obj, indent=2, ensure_ascii=False)
            )
        except Exception as e:
            logger.warning(f"[Soul] market_memory保存失败: {e}")

    def record_pattern(self, kline_df, code="", label="", future_return=0):
        """记录一个市场模式"""
        try:
            if kline_df is None or len(kline_df) < 20:
                return
            close = kline_df["close"].values
            volume = kline_df["volume"].values

            recent = close[-10:]
            ret = np.diff(recent) / np.maximum(recent[:-1], 1e-10)
            vol_change = np.mean(volume[-5:]) / max(np.mean(volume[-20:-5]), 1)

            pattern = {
                "time": datetime.now().isoformat(),
                "code": code,
                "label": label,
                "features": {
                    "last_10d_return": round((recent[-1] / recent[0] - 1) * 100, 2),
                    "max_drawdown_10d": round((np.min(recent) / np.max(recent) - 1) * 100, 2),
                    "volatility_10d": round(np.std(ret) * 100, 2),
                    "volume_ratio": round(vol_change, 2),
                    "positive_days": int(np.sum(ret > 0)),
                    "consecutive_up": self._max_consecutive(ret > 0),
                    "consecutive_down": self._max_consecutive(ret < 0),
                },
                "future_return": round(future_return * 100, 2),
            }
            self.patterns.append(pattern)
            self._save()
            logger.info(f"[Soul] record_pattern: {label} code={code} "
                         f"ret={pattern['features']['last_10d_return']}%")
        except Exception as e:
            logger.warning(f"[Soul] record_pattern 异常: {e}")

    def daily_snapshot(self, market_score: float, regime: str,
                       top_sectors: list = None, sentiment: float = None):
        """每日市场状态快照 — 记录到data/market_memory.json的daily_snapshots

        Args:
            market_score: 市场综合评分(0-100)
            regime: 市场状态(bull_strong/bull_weak/range/bear_weak/bear_strong)
            top_sectors: 前几热点板块列表
            sentiment: 情绪指数(0-100)

        保存格式(追加到daily_snapshots,保留最近365天):
        {
            "date": "2024-01-15",
            "market_score": 65,
            "regime": "bull_weak",
            "top_sectors": ["半导体", "AI"],
            "sentiment": 55,
            "features": { 用于后续match_current的匹配特征
                "score_level": "high"/"mid"/"low",
                "regime_idx": 0-4,
                "sentiment_level": "high"/"mid"/"low"
            }
        }
        """
        try:
            today = datetime.now().strftime("%Y-%m-%d")

            # 读取现有数据
            records = {"daily_snapshots": []}
            try:
                if MEMORY_FILE.exists():
                    raw = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        records = raw
                    elif isinstance(raw, list):
                        records = {"records": raw, "daily_snapshots": []}
            except Exception:
                pass

            # 今日是否已存在(避免重复记录)
            existing_dates = {s.get("date", "") for s in records.get("daily_snapshots", [])}
            if today in existing_dates:
                logger.debug(f"[Soul] daily_snapshot: {today} 已存在,跳过")
                return

            # 构建特征
            score_level = "high" if market_score >= 65 else ("low" if market_score < 40 else "mid")
            regime_map = {"bull_strong": 0, "bull_weak": 1, "range": 2, "bear_weak": 3, "bear_strong": 4}
            regime_idx = regime_map.get(regime, 2)
            sent_level = "high" if sentiment and sentiment >= 65 else ("low" if sentiment and sentiment < 40 else "mid")

            snapshot = {
                "date": today,
                "market_score": round(market_score, 1),
                "regime": regime,
                "regime_idx": regime_idx,
                "top_sectors": (top_sectors or [])[:5],
                "sentiment": round(sentiment, 1) if sentiment is not None else None,
                "features": {
                    "score_level": score_level,
                    "regime_idx": regime_idx,
                    "sentiment_level": sent_level,
                }
            }

            records.setdefault("daily_snapshots", []).append(snapshot)

            # 保留最近365天
            snapshots = records["daily_snapshots"]
            if len(snapshots) > 365:
                records["daily_snapshots"] = snapshots[-365:]

            # 保存(不破坏原有records)
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            MEMORY_FILE.write_text(
                json.dumps(records, indent=2, ensure_ascii=False)
            )
            logger.info(f"[Soul] daily_snapshot: {today} score={market_score:.0f} "
                         f"regime={regime} sentiment={sentiment}")

        except Exception as e:
            logger.warning(f"[Soul] daily_snapshot 异常: {e}")

    def match_current(self, state: dict = None) -> dict:
        """根据传入或读取的状态,匹配历史相似周期

        Args:
            state: {
                "market_score": float,
                "regime": str,
                "sentiment": float (optional),
                "top_sectors": [str] (optional)
            }
            如果state为None,使用old K线匹配(向后兼容)

        Returns:
            dict: {matches, advice, current_features, avg_future_return}
        """
        try:
            if state is not None:
                return self._match_snapshots(state)

            if not self.patterns:
                return {"current": {}, "matches": [],
                        "advice": "尚无记忆数据,请先积累", "avg_future_return": 0}

            return {"matches": [], "advice": "需要传入state参数",
                    "avg_future_return": 0}

        except Exception as e:
            logger.warning(f"[Soul] match_current 异常: {e}")
            return {"matches": [], "advice": "匹配异常", "avg_future_return": 0}

    def _match_snapshots(self, state: dict) -> dict:
        """从daily_snapshots中匹配历史相似状态"""
        result = {
            "current": state,
            "matches": [],
            "advice": "暂无足够快照数据",
            "avg_future_return": 0,
        }

        snapshots = []
        try:
            if MEMORY_FILE.exists():
                raw = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    snapshots = raw.get("daily_snapshots", [])
        except Exception:
            pass

        if not snapshots:
            return result

        curr_score = state.get("market_score", 50)
        curr_regime = state.get("regime", "range")
        curr_sentiment = state.get("sentiment", 50)
        regime_map = {"bull_strong": 0, "bull_weak": 1, "range": 2, "bear_weak": 3, "bear_strong": 4}
        curr_regime_idx = regime_map.get(curr_regime, 2)
        curr_score_level = "high" if curr_score >= 65 else ("low" if curr_score < 40 else "mid")
        curr_sent_level = "high" if curr_sentiment and curr_sentiment >= 65 else ("low" if curr_sentiment and curr_sentiment < 40 else "mid")

        current_features = {
            "score_level": curr_score_level,
            "regime_idx": curr_regime_idx,
            "sentiment_level": curr_sent_level,
        }

        def score_diff(f):
            d = 0
            d += abs(f.get("regime_idx", 2) - curr_regime_idx) * 3
            sl_map = {"high": 2, "mid": 1, "low": 0}
            d += abs(sl_map.get(f.get("score_level", "mid"), 1) - sl_map.get(curr_score_level, 1)) * 2
            d += abs(sl_map.get(f.get("sentiment_level", "mid"), 1) - sl_map.get(curr_sent_level, 1)) * 1
            return d

        today = datetime.now().strftime("%Y-%m-%d")
        scored = []
        for s in snapshots:
            if s.get("date") == today:
                continue
            f = s.get("features", {})
            if not f:
                continue
            sd = score_diff(f)
            scored.append({
                "dist": sd,
                "date": s.get("date", ""),
                "regime": s.get("regime", ""),
                "market_score": s.get("market_score", 50),
                "sentiment": s.get("sentiment"),
                "top_sectors": s.get("top_sectors", []),
            })

        if not scored:
            return result

        scored.sort(key=lambda x: x["dist"])
        top5 = scored[:5]

        recent_snapshots = [s for s in snapshots if s.get("date") != today]
        recent_snapshots = recent_snapshots[-10:]
        if len(recent_snapshots) >= 3:
            scores_trend = [s.get("market_score", 50) for s in recent_snapshots]
            if len(scores_trend) >= 3:
                first_avg = np.mean(scores_trend[:3])
                last_avg = np.mean(scores_trend[-3:])
                trend = last_avg - first_avg
                result["trend_pct"] = round(trend, 1)
                if trend > 5:
                    result["advice"] = f"近期市场评分上升{trend:.0f}分,趋势向好"
                elif trend < -5:
                    result["advice"] = f"近期市场评分下降{trend:.0f}分,注意风险"
                else:
                    result["advice"] = "近期市场状态稳定"

        result["matches"] = top5
        result["current_features"] = current_features
        result["avg_future_return"] = 0

        if top5:
            closest = top5[0]
            logger.info(f"[Soul] match_current: top_match={closest['date']} "
                         f"regime={closest['regime']} score={closest['market_score']} "
                         f"dist={closest['dist']} advice={result['advice']}")

        return result

    def _match_kline(self, kline_df) -> dict:
        """(旧版) K线形态匹配 — 向后兼容"""
        if kline_df is None or len(kline_df) < 20:
            return {}
        close = kline_df["close"].values
        volume = kline_df["volume"].values
        recent = close[-10:]
        ret = np.diff(recent) / np.maximum(recent[:-1], 1e-10)

        current_features = {
            "last_10d_return": round((recent[-1] / recent[0] - 1) * 100, 2),
            "max_drawdown_10d": round((np.min(recent) / np.max(recent) - 1) * 100, 2),
            "volatility_10d": round(np.std(ret) * 100, 2),
            "volume_ratio": round(np.mean(volume[-5:]) / max(np.mean(volume[-20:-5]), 1), 2),
            "positive_days": int(np.sum(ret > 0)),
        }

        if not self.patterns:
            return {"current": current_features, "matches": [],
                    "advice": "尚无记忆数据,请先积累"}

        matches = []
        for p in self.patterns[-50:]:
            f = p["features"]
            dist = sum((current_features.get(k, 0) - f.get(k, 0)) ** 2 for k in current_features)
            matches.append({"dist": dist, "future_return": p["future_return"],
                          "time": p["time"], "code": p["code"]})

        matches.sort(key=lambda x: x["dist"])
        top3 = matches[:3]
        avg_future = np.mean([m["future_return"] for m in top3])

        advice = ""
        if avg_future > 3:
            advice = "历史相似模式平均上涨{:.1f}%,偏乐观".format(avg_future)
        elif avg_future < -3:
            advice = "历史相似模式平均下跌{:.1f}%,注意风险".format(avg_future)
        else:
            advice = "历史相似模式涨跌不一,正常波动"

        return {"current": current_features, "matches": top3,
                "avg_future_return": round(avg_future, 2), "advice": advice}

    def _max_consecutive(self, arr) -> int:
        max_c = 0
        cur = 0
        for v in arr:
            cur = cur + 1 if v else 0
            max_c = max(max_c, cur)
        return max_c

    def get_snapshot_summary(self) -> dict:
        """获取快照摘要统计"""
        try:
            snapshots = []
            if MEMORY_FILE.exists():
                raw = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    snapshots = raw.get("daily_snapshots", [])
            return {
                "total_snapshots": len(snapshots),
                "date_range": {
                    "first": snapshots[0]["date"] if snapshots else None,
                    "last": snapshots[-1]["date"] if snapshots else None,
                },
                "regime_distribution": dict(
                    (r, sum(1 for s in snapshots if s.get("regime") == r))
                    for r in set(s.get("regime", "") for s in snapshots)
                ),
            }
        except Exception as e:
            logger.warning(f"[Soul] get_snapshot_summary 异常: {e}")
            return {"total_snapshots": 0}


# 全局实例
market_memory = MarketMemory()