"""
Agent间共享候选池 — P2升级
=========================
功能: 6个Agent各自选出的候选股去重聚合, 生成"热力图"
被≥2个Agent同时选中的股票自动加入共享watchlist
上班族中短线可以看到全职短线客发现的涨停板候选

使用方式:
    from multi_agent.shared_watchlist import SharedWatchlist
    sw = SharedWatchlist()
    sw.collect(profile_name, candidates)  # 每个Agent报告自己的候选
    heatmap = sw.get_heatmap()            # 获取热力图
"""
import json, logging, time
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("aurora.shared_watchlist")

WATCHLIST_FILE = Path(__file__).resolve().parent.parent / "data" / "shared_watchlist.json"


class SharedWatchlist:
    """Agent间候选热力图 — 共享池"""

    def __init__(self, ttl_minutes: int = 60):
        self.ttl = ttl_minutes * 60
        self.data = self._load()

    def _load(self) -> dict:
        try:
            if WATCHLIST_FILE.exists():
                d = json.loads(WATCHLIST_FILE.read_text())
                # TTL检查: 超过1小时的数据清空
                if time.time() - d.get("_ts", 0) > self.ttl:
                    return {"_ts": time.time(), "stocks": {}}
                return d
        except Exception:
            pass
        return {"_ts": time.time(), "stocks": {}}

    def _save(self):
        try:
            WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
            WATCHLIST_FILE.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.debug(f"[Shared] save: {e}")

    def collect(self, profile_name: str, candidates: list):
        """
        每个Agent报告自己的候选列表
        
        Args:
            profile_name: Agent名称
            candidates: [{"code": "...", "name": "...", "score": N, "strategy": "...", ...}]
        """
        stocks = self.data.setdefault("stocks", {})
        for c in candidates:
            code = c.get("code", "")
            if not code:
                continue
            if code not in stocks:
                stocks[code] = {
                    "code": code,
                    "name": c.get("name", ""),
                    "agents": [],
                    "strategies": [],
                    "max_score": 0,
                    "avg_score": 0,
                    "first_seen": datetime.now().strftime("%H:%M"),
                }
            entry = stocks[code]
            entry["agents"].append(profile_name)
            entry["agents"] = list(set(entry["agents"]))  # 去重
            strat = c.get("best_strategy", c.get("strategy", ""))
            if strat and strat not in entry["strategies"]:
                entry["strategies"].append(strat)
            score = c.get("best_score", c.get("score", 0))
            if score > entry["max_score"]:
                entry["max_score"] = score
            entry["avg_score"] = round(sum(
                s.get("best_score", s.get("score", 0))
                for cc in candidates if cc.get("code") == code
                for s in [cc]
            ) / max(len([cc for cc in candidates if cc.get("code") == code]), 1), 1)
        self.data["_ts"] = time.time()
        self._save()

    def get_heatmap(self, min_agents: int = 1, top_n: int = 20) -> list:
        """
        获取热力图(按Agent关注数/评分排序)
        
        Args:
            min_agents: 至少被N个Agent选中才显示
            top_n: 返回前N只
        
        Returns:
            list of dict: [{code, name, agents_count, agents, strategies, max_score, avg_score}]
        """
        stocks = self.data.get("stocks", {})
        result = []
        for code, entry in stocks.items():
            agents = entry.get("agents", [])
            if len(agents) < min_agents:
                continue
            result.append({
                "code": code,
                "name": entry.get("name", ""),
                "agents_count": len(agents),
                "agents": agents,
                "strategies": entry.get("strategies", []),
                "max_score": entry.get("max_score", 0),
                "avg_score": entry.get("avg_score", 0),
                "first_seen": entry.get("first_seen", ""),
            })
        # 排序: Agent关注数优先, 评分次之
        result.sort(key=lambda x: (-x["agents_count"], -x["avg_score"]))
        return result[:top_n]

    def get_consensus(self, min_agents: int = 3) -> list:
        """获取高度共识的热门股(被≥3个Agent选中)"""
        return self.get_heatmap(min_agents=min_agents, top_n=10)

    def clear(self):
        """清除数据"""
        self.data = {"_ts": time.time(), "stocks": {}}
        self._save()
        logger.info("[Shared] 共享池已清空")
