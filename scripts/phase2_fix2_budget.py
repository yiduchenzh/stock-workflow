# -*- coding: utf-8 -*-
"""阶段2 修复②: P1-1 画像级预算闸 — 给 AgentSimAccount 补 day_baseline()/mark_day_close()
+ 状态文件补齐 4 字段(day_open_date/day_open_total/close_date/close_total)

根因: AgentSimAccount(multi_agent/agent.py:147) 是独立包装类(非 SimAccount 子类),
      缺 day_baseline() → engine `acc.day_baseline()` 抛 AttributeError → 回退 prev_total
      (同日被 _save 刷新) → daily_pnl≡0 → 画像 risk_budget weekly_pnl 恒 1e-9。
本仓 CRLF+中文 → 用确定性替换(assert 命中/compile/read-back), 不用 patch 模糊匹配。
"""
import io
import py_compile

P = r"D:\Hermes Agent CN Desktop\stock-workflow\multi_agent\agent.py"
src = io.open(P, encoding="utf-8", newline="").read()
before = src
NL = "\r\n" if "\r\n" in src else "\n"
n_edits = 0


def rep(old, new, tag, count=1):
    global src, n_edits
    assert old in src, f"[{tag}] 锚点未命中:\n{old[:200]}"
    assert src.count(old) == count, f"[{tag}] 锚点命中 {src.count(old)} 次(期望{count})"
    src = src.replace(old, new, count)
    n_edits += 1
    print(f"  ✓ {tag}")


# ── ① __init__: 补 4 个日基准字段(在 _load() 之前, 让 _load 可覆盖) ──
rep(
    "        self.total_value = capital" + NL + "        self._load()",
    "        self.total_value = capital" + NL
    + "        # ⭐ v14.51(2026-09-18 周复盘 P1-1): 日基准字段(与 SimAccount 同口径)" + NL
    + "        self.prev_total = float(capital)   # 加载时总资产(兜底)" + NL
    + "        self.day_open_date = \"\"            # 当日基准日期" + NL
    + "        self.day_open_total = 0.0          # 当日基准总资产(当日首次固化)" + NL
    + "        self.close_date = \"\"               # 最近日终记录日期" + NL
    + "        self.close_total = 0.0             # 该日总资产(次日作基准)" + NL
    + "        self._load()",
    "__init__ 补日基准字段",
)

# ── ② _load: 读回 4 字段 ──
rep(
    "                self.prev_total = float(d.get(\"total\", self.total_value))" + NL
    + "                saved_date = d.get(\"date\", \"\")",
    "                self.prev_total = float(d.get(\"total\", self.total_value))" + NL
    + "                # ⭐ v14.51(2026-09-18 P1-1): 日基准字段落盘/读回" + NL
    + "                self.day_open_date = str(d.get(\"day_open_date\", \"\") or \"\")" + NL
    + "                self.day_open_total = float(d.get(\"day_open_total\", 0) or 0)" + NL
    + "                self.close_date = str(d.get(\"close_date\", \"\") or \"\")" + NL
    + "                self.close_total = float(d.get(\"close_total\", 0) or 0)" + NL
    + "                saved_date = d.get(\"date\", \"\")",
    "_load 读回日基准",
)

# ── ③ _save: 写 4 字段 ──
rep(
    "            \"total\": round(self.total_value, 2)," + NL
    + "            \"date\": str(datetime.now().date())," + NL
    + "        }, indent=2, ensure_ascii=False), encoding=\"utf-8\")",
    "            \"total\": round(self.total_value, 2)," + NL
    + "            \"date\": str(datetime.now().date())," + NL
    + "            # ⭐ v14.51(2026-09-18 P1-1): 日基准随状态落盘" + NL
    + "            \"day_open_date\": self.day_open_date," + NL
    + "            \"day_open_total\": round(self.day_open_total, 2)," + NL
    + "            \"close_date\": self.close_date," + NL
    + "            \"close_total\": round(self.close_total, 2)," + NL
    + "        }, indent=2, ensure_ascii=False), encoding=\"utf-8\")",
    "_save 写入日基准",
)

# ── ④ 新增 day_baseline() / mark_day_close()(语义照 SimAccount:521-550) ──
rep(
    "    def _update_total(self):",
    "    def day_baseline(self) -> float:" + NL
    + "        \"\"\"当日盈亏基准(总资产) — 每日首次调用固化并落盘, 同日复用。" + NL
    + "" + NL
    + "        ⭐ v14.51(2026-09-18 周复盘 P1-1): AgentSimAccount 原缺此方法 → engine 回退" + NL
    + "        prev_total(同日被 _save 刷新) → daily_pnl≡0 → 画像 risk_budget weekly_pnl" + NL
    + "        恒 1e-9 → 周-5%/月-8% 闸永不触发。与 SimAccount.day_baseline 同口径。" + NL
    + "        优先级: ① 昨日日终(close_total) ② 当日已固化 ③ 加载时总资产 ④ 本金。" + NL
    + "        \"\"\"" + NL
    + "        today = str(datetime.now().date())" + NL
    + "        if self.day_open_date == today and self.day_open_total > 0:" + NL
    + "            return self.day_open_total" + NL
    + "        base = 0.0" + NL
    + "        if self.close_date and self.close_date != today and self.close_total > 0:" + NL
    + "            base = self.close_total" + NL
    + "        elif getattr(self, \"prev_total\", 0) and float(self.prev_total) > 0:" + NL
    + "            base = float(self.prev_total)" + NL
    + "        if base <= 0:" + NL
    + "            base = float(self.capital)" + NL
    + "        self.day_open_date = today" + NL
    + "        self.day_open_total = float(base)" + NL
    + "        self._save()" + NL
    + "        return float(base)" + NL
    + "" + NL
    + "    def mark_day_close(self) -> float:" + NL
    + "        \"\"\"日终记录总资产(供次日作当日基准)。⭐ v14.51(2026-09-18 P1-1)\"\"\"" + NL
    + "        self.close_date = str(datetime.now().date())" + NL
    + "        self.close_total = float(self.total_value)" + NL
    + "        self._save()" + NL
    + "        return self.close_total" + NL
    + "" + NL
    + "    def _update_total(self):",
    "新增 day_baseline/mark_day_close",
)

io.open(P, "w", encoding="utf-8", newline="").write(src)
py_compile.compile(P, doraise=True)
print(f"\n✅ py_compile 通过 (共 {n_edits} 处改动, 文件 {len(before)}→{len(src)} 字符)")

back = io.open(P, encoding="utf-8", newline="").read()
assert "def day_baseline" in back and "def mark_day_close" in back
assert back.count("v14.51") == 4
print("✅ 回读复核: 新增2方法 + 4处 v14.51 标记齐全")
