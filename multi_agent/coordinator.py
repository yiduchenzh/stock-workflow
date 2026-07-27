"""多Agent协调器 — 运行6个AI交易员,各自独立模拟交易"""
import sys, json, logging, shutil
from pathlib import Path
from datetime import datetime
from multi_agent.agent import TraderAgent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("aurora.coordinator")

ALL_PROFILES = [
    "上班族中短线",
    "全职短线客",
    "趋势跟踪者",
    "新手入门",
    "消息面短线",
    "价值投资者",
]

class MultiAgentCoordinator:
    def __init__(self):
        self.agents = {}
        for name in ALL_PROFILES:
            self.agents[name] = TraderAgent(name)

    def clear_all_data(self):
        """清除所有Agent的历史数据"""
        data_root = Path(__file__).resolve().parent.parent / "data"
        count = 0
        for agent_dir in data_root.glob("agent_*/"):
            for f in agent_dir.iterdir():
                f.unlink()
                count += 1
            agent_dir.rmdir()
        # 也清空旧的统一模拟数据
        for old_f in ["sim_state.json", "sim_trades.json", "bt_vs_live.json"]:
            p = data_root / old_f
            if p.exists():
                p.unlink()
                count += 1
        logger.info(f"[Coord] 已清除{count}个旧数据文件")
        # 重新初始化
        self.__init__()
        return count

    def run_all_morning(self):
        """所有Agent执行晨盘"""
        results = {}
        for name, agent in self.agents.items():
            try:
                agent.run_morning()
                results[name] = agent.get_summary()
                logger.info(f"[Coord] {name} 晨盘完成: {results[name]['total_value']:.0f}")
            except Exception as e:
                logger.error(f"[Coord] {name} 晨盘失败: {e}")
                results[name] = {"error": str(e)}
        self._save_aggregate()
        # ── P2升级: 收集Agent候选到共享池 ──
        self._collect_shared_candidates(results)
        return results

    def run_all_intraday(self):
        """所有Agent执行盘中扫描"""
        results = {}
        for name, agent in self.agents.items():
            try:
                agent.run_intraday()
                results[name] = agent.get_summary()
            except Exception as e:
                logger.error(f"[Coord] {name} 盘中失败: {e}")
        self._save_aggregate()
        # ── P2升级: 收集Agent候选到共享池 ──
        self._collect_shared_candidates(results)
        return results

    def _collect_shared_candidates(self, results: dict):
        """收集每个Agent的候选股到共享池"""
        try:
            from multi_agent.shared_watchlist import SharedWatchlist
            sw = SharedWatchlist()
            for name in self.agents:
                agent = self.agents.get(name)
                if agent and agent.engine:
                    candidates = getattr(agent.engine, 'candidates', None) or getattr(agent.engine, 'analysis', None) or []
                    if candidates:
                        sw.collect(name, candidates)
            heatmap = sw.get_heatmap(min_agents=2)
            if heatmap:
                logger.info(f"[Shared] 多Agent共识候选: {len(heatmap)}只")
                for s in heatmap[:5]:
                    logger.info(f"  ⭐ {s['code']} {s['name']}: {s['agents_count']}个Agent {s['strategies']}")
            else:
                logger.info("[Shared] 无2+Agent共识候选")
        except Exception as e:
            logger.debug(f"[Shared] collect: {e}")

    def _save_aggregate(self):
        """保存汇总状态"""
        summaries = {n: a.get_summary() for n, a in self.agents.items()}
        report = {
            "time": datetime.now().isoformat(),
            "agents": summaries,
            "total_capital": sum(s.get("capital", 1_000_000) for s in summaries.values()),
            "total_value": sum(s.get("total_value", 0) for s in summaries.values()),
        }
        data_dir = Path(__file__).resolve().parent.parent / "data"
        (data_dir / "agent_aggregate.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False))

    def get_aggregate_report(self) -> dict:
        """生成汇总报告(用于推送)"""
        summaries = {n: a.get_summary() for n, a in self.agents.items()}
        lines = []
        for name, s in summaries.items():
            pnl_str = f"+{s['return_pct']:.1f}%" if s['return_pct'] >= 0 else f"{s['return_pct']:.1f}%"
            lines.append(f"  {name}: {s['total_value']:.0f}元 ({pnl_str}) 持仓{s['positions']}只")
        return {
            "time": datetime.now().strftime("%H:%M"),
            "agents": len(self.agents),
            "summary": "\n".join(lines),
            "total_capital": sum(s.get("capital", 1_000_000) for s in summaries.values()),
            "total_value": sum(s.get("total_value", 0) for s in summaries.values()),
        }

    def push_aggregate_report(self):
        """推送各Agent交易执行明细(分类标注)到主引擎"""
        import yaml
        cfg_path = Path(__file__).resolve().parent.parent / "config.yaml"
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
            sct = cfg.get("notify",{}).get("sct_token","")
            if not sct: return
            report = self.get_aggregate_report()
            title = "Aurora 6AI交易员 " + report['time']
            msg_lines = [f"【6Agent汇总】"]
            for line in report['summary'].split(chr(10)):
                msg_lines.append(line.strip())
            msg_lines.append(f"总资产: {report['total_value']:.0f}元")
            msg_lines.append("")
            # 各Agent交易明细
            for name, agent in self.agents.items():
                acct = agent.account
                if not acct:
                    continue
                trades = acct.trades if hasattr(acct, 'trades') else []
                today = datetime.now().strftime("%Y-%m-%d")
                today_trades = [t for t in trades if str(t.get("time",""))[:10] == today]
                if not today_trades:
                    continue
                buys = [t for t in today_trades if t.get("action") == "buy"]
                sells = [t for t in today_trades if t.get("action") == "sell"]
                if buys or sells:
                    msg_lines.append(f"【{name}】")
                    if buys:
                        for t in buys[-3:]:
                            msg_lines.append(f"  🟢买入 {t.get('code','?')} {t.get('shares',0)}股 @{t.get('price',0):.2f}")
                    if sells:
                        for t in sells[-3:]:
                            pnl = t.get('pnl',0)
                            pnl_s = f"盈亏{pnl:+.0f}元" if pnl else ""
                            msg_lines.append(f"  🔴卖出 {t.get('code','?')} {t.get('shares',0)}股 @{t.get('price',0):.2f} {pnl_s}")
            msg = chr(10).join(msg_lines)
            import requests
            requests.post(f"https://sctapi.ftqq.com/{sct}.send",
                data={"title":title,"desp":msg}, timeout=10)
            logger.info(f"[Coord] 分类推送完成: {report['agents']}个Agent")
        except Exception as e:
            logger.warning(f"[Coord] 推送失败: {e}")

def run_multi_pipeline():
    """一键运行: 清除旧数据 → 启动6个Agent → 推送报告"""
    coord = MultiAgentCoordinator()
    coord.clear_all_data()
    logger.info("[Pipeline] 旧数据已清除,6个账户初始化完成")
    results = coord.run_all_morning()
    coord.push_aggregate_report()
    return coord, results
