"""Aurora 守护进程 — 自动运行已禁用 (2026-07-28)
如需重新启用: git restore scripts/daemon_launcher.py
"""
import logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("aurora.daemon")
log.warning("=" * 60)
log.warning("  Aurora 自动运行已禁用")
log.warning("  如需启用: git restore scripts/daemon_launcher.py")
log.warning("=" * 60)
