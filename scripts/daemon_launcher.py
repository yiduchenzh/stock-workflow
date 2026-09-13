# -*- coding: utf-8 -*-
"""Aurora 守护进程 launcher — 启动实时流引擎（2026-08-09 重建）

原文件被一次失败的 git show 恢复操作覆盖损坏（内容变成 git 错误文本）。
本文件 = 启用版：调用 core/engine_live.start_live_engine() 常驻运行
（EngineLiveWrapper.run_forever, 60s 周期: 市场刷新+盘中扫描+心跳+崩溃恢复）。
start_daemon.bat 用窗口标题 "aurora_daemon" 匹配启停。
"""
import logging
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ═══ 单实例锁（端口 8123）：防止计划任务/手动重复拉起守护实例 ═══
# listen(64): 锁只做 bind 占用, 不 accept; backlog 足够大避免探测连接(健康监控)占满队列
_LOCK_PORT = 8123
try:
    _lock_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _lock_sock.bind(("127.0.0.1", _LOCK_PORT))
    _lock_sock.listen(64)
except OSError:
    print("daemon already running (port 8123 locked), exit.")
    sys.exit(0)

from core.engine_live import start_live_engine

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(str(Path(__file__).resolve().parent.parent / "logs" / "daemon.log"),
                                encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    start_live_engine(interval=60)
