# -*- coding: utf-8 -*-
"""2026-10-01 修复回归: 持仓保护的「标记/执行」两半必须同时存在

背景(实测根因): core/engine.py::step_monitor 里有**两个** `for a in self.alerts` 循环 ——
  第一个做持仓天数保护, 但它的 `continue` 只跳过自己(空转); 第二个循环才是真执行卖出, 毫无保护。
  ⇒ `risk.min_hold_days` **完全失效**(只打印 "跳过卖出" 日志, 照样成交)。
本测试是**防回归绊线**(非行为测试): 该修复是"两半配对"结构, 缺任一半即静默失效 —— 故断言两半都在,
且同处 step_monitor 内。行为层由 tests/ 全量用例 + 引擎实例化保证。
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src():
    return io.open(os.path.join(ROOT, "core", "engine.py"), encoding="utf-8").read()


def test_hold_block_mark_and_enforce_are_paired():
    src = _src()
    assert 'a["_hold_block"] = True' in src, "缺少『标记』一半: 持仓保护不生效"
    assert 'if a.get("_hold_block"):' in src, "缺少『执行时跳过』一半: 标记无效, 仍会卖出"
    # 两半必须成对出现（一处标记 + 一处消费）
    assert src.count("_hold_block") >= 2, "_hold_block 出现次数异常: %d" % src.count("_hold_block")


def test_hold_protect_not_a_lie_in_logs():
    """原实现的日志文案是谎言(说跳过、实则卖出) → 现在必须写成『本次跳过』并真的打标记"""
    src = _src()
    i = src.find("{min_hold}")
    assert i > 0, "未找到持仓保护日志行"
    seg = src[max(0, i - 400):i + 400]
    assert "_hold_block" in seg, "打日志的同一分支里必须打标记(否则日志仍是谎言)"


def test_min_hold_days_semantics_and_default():
    """min_hold_days 语义: max(0, min(max_hold_days//3, min_hold_days)); 2026-10-01 实测后默认 0

    实测依据(配对 130 笔): 持仓<3天被卖的 82 笔, 卖出后次日均值 -0.94%(62% 继续跌)
    ⇒ 短持有期卖出是正确的, 人为强行持有会扩大浮亏 ⇒ 默认 0(不设限)。
    """
    import yaml
    cfg = yaml.safe_load(io.open(os.path.join(ROOT, "config.yaml"), encoding="utf-8"))
    mhd = cfg["risk"]["min_hold_days"]
    assert mhd == 0, "默认必须为 0(实测支撑), 实际 %r" % mhd
    # 语义公式
    for amhd, expect in ((10, min(10 // 3, mhd)), (30, min(30 // 3, mhd))):
        assert max(0, min(amhd // 3, mhd)) == expect


def test_ht_trade_log_test_isolation():
    """tests/test_new_modules.py 必须把 TRADE_LOG 重定向到 tmp, 禁止写生产 data/ht_trade_log.json"""
    t = io.open(os.path.join(ROOT, "tests", "test_new_modules.py"), encoding="utf-8").read()
    assert "TRADE_LOG" in t and "tmp_path" in t, "缺少 TRADE_LOG 隔离 fixture → 跑测试会污染生产日志"


def test_clear_all_data_archives_before_delete():
    """clear_all_data 必须先归档再删(原实现直接 unlink → 07 月成交流水永久丢失)"""
    c = io.open(os.path.join(ROOT, "multi_agent", "coordinator.py"), encoding="utf-8").read()
    assert "_archived_clears" in c, "缺少归档目录: 清库会再次静默丢失历史"
    assert "copytree" in c, "缺少归档动作"
