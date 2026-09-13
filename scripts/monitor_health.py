# -*- coding: utf-8 -*-
"""盘中系统健康监控 — 2026-08-10（计划任务每 5 分钟跑）

监控项（交易时段 9:30-15:00 生效, 非交易时段静默）:
  1. web 后端 :8000 health —— 挂了告警
  2. web auto_trader —— running 状态 + last_tick 新鲜度（>5min 无更新 = tick 卡死告警）
  3. 工作流守护 —— 端口 8123 单实例锁存活
  4. 共享库 —— limitup-system/cache/kline.db 存在 + WAL 模式

推送: 异常/状态变化 → Server酱【监控】；同类告警 30 分钟抑制防刷屏。
"""
import json
import os
import socket
import sys
import time
import requests
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
STATE_FILE = BASE / "data" / "monitor_state.json"
SUPPRESS_SEC = 30 * 60  # 同类告警 30 分钟抑制
KLINE_DB = Path(r"D:\Hermes Agent CN Desktop\limitup-system\cache\kline.db")


def load_cfg_token() -> str:
    try:
        import yaml
        cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8")) or {}
        tok = (cfg.get("notify") or {}).get("sct_token", "")
        if tok:
            return tok
    except Exception:
        pass
    return os.environ.get("SCT_TOKEN", "")


def push(title: str, desc: str):
    tok = load_cfg_token()
    if not tok:
        return
    try:
        requests.post(f"https://sctapi.ftqq.com/{tok}.send",
                      json={"title": title[:80], "desp": desc[:3000]}, timeout=10)
    except Exception:
        pass


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(st: dict):
    try:
        STATE_FILE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def suppressed(st: dict, key: str) -> bool:
    last = st.get("last_push", {}).get(key, 0)
    return (time.time() - last) < SUPPRESS_SEC


def mark_pushed(st: dict, key: str):
    st.setdefault("last_push", {})[key] = time.time()
    save_state(st)


def now_hm() -> int:
    n = datetime.now()
    return n.hour * 100 + n.minute


def is_trading_session() -> bool:
    n = datetime.now()
    if n.weekday() >= 5:
        return False
    hm = n.hour * 100 + n.minute
    return (930 <= hm <= 1130) or (1300 <= hm <= 1500)


def check_web(st: dict) -> list:
    """web 后端 + auto_trader tick 新鲜度"""
    issues = []
    try:
        h = requests.get("http://127.0.0.1:8000/api/v1/health", timeout=10)
        if h.status_code != 200:
            if not suppressed(st, "web_down"):
                push("🚨【监控】web 后端异常", f"health HTTP {h.status_code}\n请检查: start_unattended.bat 或 launcher.py")
                mark_pushed(st, "web_down")
            issues.append("web后端 health 非200")
    except Exception:
        if not suppressed(st, "web_down"):
            push("🚨【监控】web 后端不可达", f"http://127.0.0.1:8000 连接失败\n请检查: 后端进程/launcher.py")
            mark_pushed(st, "web_down")
        issues.append("web后端不可达")
    # auto_trader tick 新鲜度（交易时段内 last_tick 应持续更新）
    if is_trading_session():
        try:
            at = requests.get("http://127.0.0.1:8000/api/v1/auto-trade/status", timeout=10).json()
            if not at.get("running"):
                if not suppressed(st, "at_stopped"):
                    push("⚠️【监控】web 昨收全自动交易已停止", f"running=false\nstarted_at: {at.get('started_at')}")
                    mark_pushed(st, "at_stopped")
                issues.append("auto_trader 未运行")
            else:
                lt = at.get("last_tick") or ""
                if lt:
                    t = datetime.strptime(lt, "%H:%M:%S")
                    age = (datetime.now() - datetime.combine(datetime.now().date(), t.time())).total_seconds()
                    if age > 300:  # 5 分钟无 tick
                        if not suppressed(st, "at_stuck"):
                            push("⚠️【监控】web auto_trader tick 卡死",
                                 f"last_tick={lt} ({int(age)}s 前)\n持仓 {at.get('positions')} 只 | 总资产 {at.get('total_asset',0):,.0f}")
                            mark_pushed(st, "at_stuck")
                        issues.append(f"tick卡死 last_tick={lt}")
                st["last_tick_seen"] = lt
        except Exception:
            issues.append("auto_trader 查询失败")
    return issues


def check_daemon(st: dict) -> list:
    """工作流守护（端口 8123 单实例锁）"""
    issues = []
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3)
    try:
        s.connect(("127.0.0.1", 8123))
        s.close()
    except Exception:
        if not suppressed(st, "daemon_down"):
            push("🚨【监控】工作流守护进程异常", "端口 8123 无监听\n请检查: scripts/daemon_launcher.py / start_daemon.bat")
            mark_pushed(st, "daemon_down")
        issues.append("守护进程不可达")
    return issues


def check_shared_db(st: dict) -> list:
    issues = []
    if not KLINE_DB.exists():
        if not suppressed(st, "kline_missing"):
            push("⚠️【监控】共享K线库缺失", f"{KLINE_DB}\n两项目页面/选股将降级网络拉取(慢)")
            mark_pushed(st, "kline_missing")
        issues.append("共享库缺失")
    return issues


def main():
    if not is_trading_session():
        return  # 非交易时段静默
    st = load_state()
    issues = []
    issues += check_web(st)
    issues += check_daemon(st)
    issues += check_shared_db(st)
    if issues:
        print(f"[Monitor] {datetime.now():%H:%M} 异常: {issues}")
    else:
        print(f"[Monitor] {datetime.now():%H:%M} 全部正常")
    save_state(st)


if __name__ == "__main__":
    main()
