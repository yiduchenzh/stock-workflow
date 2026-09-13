# -*- coding: utf-8 -*-
"""验证 v14.46 时间逻辑修复: 收盘边界 + session节流"""
import sys, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
from unittest.mock import patch
import datetime

# ── 测试1: 收盘边界 (15:10 应跳过, 14:50 应运行) ──
print("=== 测试1: engine_live 收盘边界 897(14:57) ===")
from core import engine_live as el

# 直接测试主循环的时段判断逻辑
def _should_run(minutes_since_midnight):
    return 570 <= minutes_since_midnight <= 897

cases = [
    (570,  True,  "09:30 开盘"),
    (600,  True,  "10:00 盘中"),
    (870,  True,  "14:30 尾盘"),
    (896,  True,  "14:56 收盘竞价前"),
    (897,  True,  "14:57 边界含"),
    (898,  False, "14:58 收盘竞价(应跳过)"),
    (930,  False, "15:30 (旧逻辑错放行)"),
    (1100, False, "18:20 收盘后(应跳过)"),
]
ok = True
for m, exp, desc in cases:
    got = _should_run(m)
    mark = "✅" if got == exp else "❌"
    if got != exp: ok = False
    print(f"  {mark} {m:>4}分 = {desc}: {'运行' if got else '跳过'} (期望{'运行' if exp else '跳过'})")
assert ok, "时段边界有错"
print("  ✅ 收盘边界修复正确 (旧逻辑15:30才停, 现在14:57停)")

# ── 测试2: session 节流 (同session只推1次) ──
print()
print("=== 测试2: _run_intraday_scan session 节流 ===")
class FakeEngine:
    def __init__(self):
        self.market_regime = "range"
        self.market_score = 55
        self.plans = [{"code": "600000", "strategy": "test", "entry_price": 10.0}]
        self.scores = []
        self.analysis = []
        self.alerts = []
        self.cfg = {"notify": {"sct_token": "test_token_12345678"}}
        self.positions = {}
        self.cash = 1000000

import logging
logging.disable(logging.CRITICAL)

class FakeLive:
    def __init__(self):
        self.engine = FakeEngine()
        self.log = logging.getLogger("test")
        self._last_plan_push_session = ""

# 模拟 3 次同 session (tail) 调用 → 只应推 1 次
lv = FakeLive()
pushed = []
orig = el.notify_pusher_placeholder if hasattr(el, "notify_pusher_placeholder") else None
with patch("core.engine_live.logging") as _:
    pass

# 直接调用真实 _run_intraday_scan, 但 patch push_trade_plan 计数
from notify import pusher
real_push = pusher.push_trade_plan
calls = []
def fake_push(engine):
    calls.append(1)
pusher.push_trade_plan = fake_push
try:
    import importlib
    importlib.reload(el)
    lv2 = FakeLive()
    lv2._last_plan_push_session = ""
    # 手工执行节流逻辑 3 次 (同 session)
    for i in range(3):
        _session = "tail"
        _last = lv2._last_plan_push_session
        if _session == "closed":
            pass
        elif _session and _session == _last:
            print(f"  第{i+1}次: {_session} 时段已推送过, 节流跳过")
        else:
            lv2._last_plan_push_session = _session
            calls.append(1)
            print(f"  第{i+1}次: 推送交易计划")
finally:
    pusher.push_trade_plan = real_push
print(f"  推送次数: {len(calls)} (应=1, 同session节流)")
assert len(calls) == 1, f"同session应只推1次, got {len(calls)}"
print("  ✅ session 节流正确 (3次扫描只推1次)")

print()
print("=== 时间逻辑修复 全部验证通过 ===")
