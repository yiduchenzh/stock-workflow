# -*- coding: utf-8 -*-
"""跨体系持仓去重 (v14.49, 2026-09-11, P1-3)

背景(2026-09-11 周复盘实证):
  主sim 与 上班族中短线 Agent 本周 5 笔同(日,票)买入 —— 300697/300913/603938/601949/002531
  (同一 prev_close_B 信号池: 主sim 11:01 买入 / Agent 10:06 或 13:06 买入),
  这 5 票本周卖出已实现 -6,177 元 = 两账户合计已实现亏损(-12,984)的 48%(601949 单票双亏)。
  原去重只覆盖 Agent 之间(multi_agent/coordinator 的 held_global), 主sim 与 Agent 之间没有。

实现: 直接读盘(sim_state.json + agent_*/state.json) → 返回"非本账户持有"的全部持仓代码。
  传 own_state_path(本账户状态文件) → 自动排除自己, 主sim/Agent 双向通用, 无需额外标记。
  带 TTL 内存缓存(默认 20s), 避免每轮 cascade 都读盘。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, Set

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
_TTL = 20.0
_cache: dict = {"ts": 0.0, "by_path": {}}          # by_path: {abs path str: set(codes)}


def _codes_of(path: Path) -> Set[str]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        pos = d.get("positions") or {}
        if isinstance(pos, dict):
            return {str(c) for c in pos.keys()}
        if isinstance(pos, list):                   # ts2 形态: list of {code}
            return {str(p.get("code")) for p in pos if isinstance(p, dict) and p.get("code")}
    except Exception:
        pass
    return set()


def _all_state_files() -> list:
    files = [DATA / "sim_state.json"]
    files += sorted(DATA.glob("agent_*/state.json"))
    return [f for f in files if f.exists()]


def held_by_others(own_state_path: Optional[object] = None) -> Set[str]:
    """返回"除自己以外"全系统已持仓代码集合.

    own_state_path: 本账户状态文件路径(SimAccount.state_path); None = 不排除任何账户.
    """
    now = time.time()
    own = str(Path(own_state_path).resolve()) if own_state_path else ""
    if now - _cache["ts"] > _TTL:
        per = {str(f.resolve()): _codes_of(f) for f in _all_state_files()}
        _cache.update({"ts": now, "by_path": per})
    out: Set[str] = set()
    for p, codes in _cache["by_path"].items():
        if own and p == own:
            continue
        out |= codes
    return out
