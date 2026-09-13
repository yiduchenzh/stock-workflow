"""
SSE事件管理器 — 一对多推送
引擎→SSE→前端，无需前端轮询
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, Any

_queues: dict[str, list[asyncio.Queue]] = {}
_lock = asyncio.Lock()

async def subscribe(topic: str = "live") -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    async with _lock:
        if topic not in _queues:
            _queues[topic] = []
        _queues[topic].append(q)
    return q

def _do_unsubscribe(topic: str, q: asyncio.Queue):
    if topic in _queues and q in _queues[topic]:
        _queues[topic].remove(q)

def unsubscribe(topic: str, q: asyncio.Queue):
    import warnings
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            loop.call_soon_threadsafe(_do_unsubscribe, topic, q)
        else:
            _do_unsubscribe(topic, q)
    except RuntimeError:
        _do_unsubscribe(topic, q)

async def publish(topic: str, event_type: str, data: Any):
    payload = {"type": event_type, "data": data, "ts": datetime.now().isoformat()}
    async with _lock:
        subs = list(_queues.get(topic, []))
    for q in subs:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
                q.put_nowait(payload)
            except asyncio.QueueEmpty:
                pass

async def event_generator(topic: str = "live") -> AsyncGenerator[str, None]:
    q = await subscribe(topic)
    try:
        yield f"event: connected\ndata: {json.dumps({'status':'ok','topic':topic})}\n\n"
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30.0)
                yield f"event: {msg['type']}\ndata: {json.dumps(msg['data'], ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                yield f"event: heartbeat\ndata: {json.dumps({'ts': datetime.now().isoformat()})}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        unsubscribe(topic, q)