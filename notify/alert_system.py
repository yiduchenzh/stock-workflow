"""异常告警体系 v1.0 — 系统健康检查 + Server酱推送"""
import json, logging, os, requests
from datetime import datetime
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
ALERT_HISTORY_FILE = PROJ / "data" / "alert_history.json"
logger = logging.getLogger("aurora.alert_system")

# 告警级别
INFO = "INFO"
WARNING = "WARNING"
CRITICAL = "CRITICAL"

_LEVEL_EMOJI = {INFO: "ℹ️", WARNING: "⚠️", CRITICAL: "🚨"}
_LEVEL_SCORE = {INFO: 10, WARNING: 50, CRITICAL: 100}


def _load_alert_history() -> list:
    if not ALERT_HISTORY_FILE.exists():
        return []
    try:
        return json.loads(ALERT_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[Alert] 加载告警历史失败: {e}")
        return []


def _save_alert_history(history: list):
    ALERT_HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_sct_token(engine=None) -> str:
    """获取Server酱Token: 优先engine.cfg, 其次环境变量"""
    token = ""
    if engine:
        token = engine.cfg.get("notify", {}).get("sct_token", "")
    if not token:
        token = os.environ.get("SCT_TOKEN", "")
    if not token and engine:
        try:
            with open(PROJ / "config.yaml") as f:
                import yaml
                cfg = yaml.safe_load(f)
                token = cfg.get("notify", {}).get("sct_token", "")
        except Exception:
            pass
    return token


def check_system_health(engine) -> dict:
    """
    检查系统健康状态
    返回: {
        "healthy": bool,
        "checks": {
            "pipeline_active": bool,
            "candidates_nonzero": bool,
            "circuit_breaker_active": bool,
            "api_available": bool,
            "market_connected": bool,
        },
        "issues": [str],
        "alert_level": str,
    }
    """
    issues = []
    checks = {}

    # 1. 管线是否中断 (有最近的candidates/analysis)
    candidates = getattr(engine, "candidates", None)
    analysis = getattr(engine, "analysis", None)
    pipeline_active = (candidates is not None and len(candidates) > 0) or \
                      (analysis is not None and len(analysis) > 0)
    checks["pipeline_active"] = pipeline_active
    if not pipeline_active:
        issues.append("管线中断: 无候选股/分析结果")

    # 2. 候选是否为零
    candidates_nonzero = candidates is not None and len(candidates) > 0
    checks["candidates_nonzero"] = candidates_nonzero
    if candidates is not None and len(candidates) == 0:
        issues.append("候选股为零 (可能市场无机会或数据源异常)")

    # 3. 熔断是否激活
    try:
        from risk.controls import check_all
        risk_result = check_all([], cfg=getattr(engine, "cfg", {}))
        circuit_breaker = risk_result.get("circuit_breaker", False) if isinstance(risk_result, dict) else False
    except Exception:
        circuit_breaker = False
    checks["circuit_breaker_active"] = circuit_breaker
    if circuit_breaker:
        issues.append("熔断已激活 — 停止所有交易")

    # 4. API是否可用 (检查数据源)
    api_available = True
    try:
        from data.sources import get_index_snapshot
        idx = get_index_snapshot(["000001"])
        if idx is None:
            api_available = False
            issues.append("数据源API不可用: get_index_snapshot返回None")
    except Exception as e:
        api_available = False
        issues.append(f"数据源API异常: {e}")
    checks["api_available"] = api_available

    # 5. 市场连接 (检查腾讯行情)
    market_connected = True
    try:
        import urllib.request
        r = urllib.request.urlopen("https://qt.gtimg.cn/q=sh000001", timeout=5)
        raw = r.read().decode("gbk", "replace")
        if "~" not in raw:
            market_connected = False
            issues.append("行情源异常: 腾讯行情返回格式异常")
    except Exception as e:
        market_connected = False
        issues.append(f"行情源连接失败: {e}")
    checks["market_connected"] = market_connected

    # 综合评定
    num_issues = len(issues)
    if num_issues == 0:
        alert_level = INFO
        healthy = True
    elif num_issues <= 2:
        alert_level = WARNING
        healthy = True
    else:
        alert_level = CRITICAL
        healthy = False

    return {
        "healthy": healthy,
        "checks": checks,
        "issues": issues,
        "alert_level": alert_level,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def push_alert(alert_type: str, message: str, engine=None):
    """
    通过Server酱推送异常告警
    alert_type: INFO / WARNING / CRITICAL
    message: 告警正文
    """
    now = datetime.now()
    emoji = _LEVEL_EMOJI.get(alert_type, "📢")
    title = f"{emoji}【工作流】告警 [{alert_type}] {now:%m-%d %H:%M}"

    # 格式化消息
    nl = chr(10)
    lines = [
        f"级别: {alert_type}",
        f"时间: {now:%Y-%m-%d %H:%M:%S}",
        "",
        message,
    ]
    desc = nl.join(lines)

    # 记录到本地历史
    history = _load_alert_history()
    history.append({
        "type": alert_type,
        "message": message,
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
    })
    # 保留最近100条
    if len(history) > 100:
        history = history[-100:]
    _save_alert_history(history)

    # Server酱推送
    token = _get_sct_token(engine)
    if not token or len(token) < 10:
        logger.info(f"[Alert] 无有效SCT_TOKEN,跳过推送: {title[:30]}...")
        return False

    # ⭐ 2026-08-10: 同一条告警只推一次（24h 窗口去重）
    try:
        from notify.dedup import should_push
        if not should_push("alert", title, desc):
            logger.info(f"[Alert] 去重跳过(24h内已推): {title[:30]}...")
            return False
    except Exception:
        pass

    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{token}.send",
            json={"title": title, "desp": desc},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"[Alert] 推送成功: {title[:30]}...")
            return True
        else:
            logger.warning(f"[Alert] 推送失败: HTTP {resp.status_code}")
            return False
    except Exception as e:
        logger.warning(f"[Alert] 推送异常: {e}")
        return False
