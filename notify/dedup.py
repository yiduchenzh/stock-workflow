# -*- coding: utf-8 -*-
"""推送去重模块 — 同一条内容只推一次（2026-08-10 用户要求）

策略: 内容指纹（kind + 去时间戳标题 + 描述主体前150字符）→ hash
同一指纹在窗口内（默认 24h）只允许推送一次；持久化 data/push_dedup.json（跨进程/重启）。

注意: 交易执行类推送每次内容不同（代码/价格/理由不同）→ 不撞指纹, 正常推送；
晨报/告警/计划等重复内容 → 撞指纹, 只推一次。
"""
import hashlib
import json
import re
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DEDUP_FILE = BASE / "data" / "push_dedup.json"
DEFAULT_WINDOW = 24 * 3600  # 同内容 24h 只推一次


def _load() -> dict:
    try:
        return json.loads(DEDUP_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d: dict):
    try:
        # 只保留最近 500 条指纹, 防文件无限膨胀
        if len(d) > 500:
            oldest = sorted(d, key=lambda k: d[k])[:-500]
            for k in oldest:
                d.pop(k, None)
        DEDUP_FILE.write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass


def _strip_time(text: str) -> str:
    """去掉时间戳/日期/秒, 避免同内容因时间不同误判为不同"""
    text = re.sub(r"\d{4}-\d{2}-\d{2}", "D", text)
    text = re.sub(r"\d{1,2}:\d{2}(:\d{2})?", "T", text)
    return text


def dedup_key(kind: str, title: str, desc: str, body_only: bool = False) -> str:
    if body_only:
        # v14.46: 仅标题指纹 — 交易计划类推送(desc含不同股票代码, 用desc会永不撞指纹→刷屏)
        body = _strip_time(kind) + "|" + _strip_time(title)
    else:
        body = _strip_time(title) + "|" + _strip_time(desc[:150])
    return hashlib.md5(body.encode("utf-8", "ignore")).hexdigest()[:20]


def should_push(kind: str, title: str, desc: str, window: float = DEFAULT_WINDOW,
                body_only: bool = False) -> bool:
    """返回 True=允许推送（并记录指纹）；False=窗口内已推过, 跳过"""
    d = _load()
    key = dedup_key(kind, title, desc, body_only=body_only)
    now = time.time()
    last = d.get(key, 0)
    if last and (now - last) < window:
        return False
    d[key] = now
    _save(d)
    return True
