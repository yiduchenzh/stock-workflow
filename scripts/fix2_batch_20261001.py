# -*- coding: utf-8 -*-
"""2026-10-01 计划修复批次2:
 A 单日开仓笔数上限(实测支撑: 当天第1笔 +0.22%/笔, 第2笔 -2.48%, 第3+笔 -2.41%)
 B 滑点 tick 校准(实测: 单笔占成交额中位 0.0010% → 冲击可忽略; 真实≈1跳 0.047%/边, 模型实收 0.272%/边)
"""
import io
import os
import py_compile
import shutil
from datetime import datetime

ROOT = r"D:\Hermes Agent CN Desktop\stock-workflow"
BAK = os.path.join(ROOT, "_restore", "fix2_20261001_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
os.makedirs(BAK, exist_ok=True)


def apply(path, edits, must_compile=True):
    full = os.path.join(ROOT, path)
    shutil.copy2(full, os.path.join(BAK, os.path.basename(path)))
    raw = io.open(full, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    src = raw.replace("\r\n", "\n")
    print("  [%s] 行尾=%s" % (path, "CRLF" if nl == "\r\n" else "LF"))
    for i, (old, new, tag) in enumerate(edits, 1):
        o = old.replace("\r\n", "\n"); n = new.replace("\r\n", "\n")
        if tag in src and n in src:
            print("  [SKIP-已应用] #%d %s" % (i, tag)); continue
        c = src.count(o)
        assert c == 1, "锚点未命中 %s #%d(%s) count=%d" % (path, i, tag, c)
        src = src.replace(o, n, 1)
        print("  [OK] %s #%d %s" % (path, i, tag))
    out = src.replace("\n", nl) if nl == "\r\n" else src
    if must_compile:
        tmp = full + ".chk.py"; io.open(tmp, "w", encoding="utf-8", newline="").write(out)
        py_compile.compile(tmp, doraise=True); os.remove(tmp)
        print("  [COMPILE-OK] %s" % path)
    io.open(full, "w", encoding="utf-8", newline="").write(out)


print("=" * 80); print("A+B sim_account.py"); print("=" * 80)
apply("executor/sim_account.py", [
    (
        '''        ms = self._get_micro_slippage(code, shares, price, is_buy=True)
        slippage = ms["slippage"]
        fill_price = ms["fill_price"]''',
        '''        # ⭐ 2026-10-01 (月度复盘) 单日开仓笔数上限
        #   实测(FIFO 配对 130 笔, 按当天下单次序分组):
        #     第1笔 +0.22%/笔(胜率38%, 仓位均值2.5万) | 第2笔 -2.48%/笔 | 第3笔及以后 -2.41%/笔(胜率22~24%)
        #   ⇒ 当天越晚的信号越差; 默认上限 2 笔(0=不限, 恢复旧行为)
        try:
            _cfg0 = self.config or {}
            _cap = (_cfg0.get("max_opens_per_day")
                    or (_cfg0.get("execution") or {}).get("max_opens_per_day")
                    or (_cfg0.get("risk") or {}).get("max_opens_per_day"))
            _cap = 2 if _cap is None else int(_cap)
        except Exception:
            _cap = 2
        if _cap > 0:
            _today0 = str(datetime.now().date())
            if getattr(self, "_open_day", "") != _today0:
                self._open_day = _today0
                self._open_count = 0
            if getattr(self, "_open_count", 0) >= _cap:
                return {"success": False,
                        "error": f"单日开仓上限{_cap}笔(当日已{self._open_count}笔;"
                                 f" 实测当天第2笔起期望-2.4%/笔)"}

        ms = self._get_micro_slippage(code, shares, price, is_buy=True)

        # ⭐ 2026-10-01 滑点口径校准(实测, 2026-10-01 月度复盘):
        #   单笔金额占当日成交额 中位 0.0010%(90分位 0.0031%) ⇒ 冲击成本可忽略;
        #   真实滑点 ≈ 1跳(0.01/价格): 中位 0.047%/边, 均值 0.069%/边;
        #   而模型实收 中位 0.272%/边 ⇒ **高估 5.8 倍**(往返虚增约 0.45%/笔)。
        #   mode: tick(默认, 贴近真实) | legacy(旧口径, 与历史 P&L 可比)
        _smode = "tick"
        try:
            _c = self.config or {}
            _smode = str(_c.get("slippage_mode")
                         or (_c.get("execution") or {}).get("slippage_mode") or "tick").lower()
        except Exception:
            _smode = "tick"
        if _smode != "legacy" and price > 0:
            _tick = 0.01 / price
            _turn = float((self._stock_micro_cache.get(code) or {}).get("avg_daily_turnover") or 5e8)
            _part_pct = (shares * price) / _turn * 100.0            # 参与度 %
            _impact = 0.1 * (_part_pct ** 0.5) / 100.0              # 平方根冲击律(1%参与度→0.1%)
            _slip = max(_tick, min(0.001, _impact))
            ms = dict(ms)
            ms["slippage"] = _slip
            ms["fill_price"] = price * (1 + _slip) if is_buy else price * (1 - _slip)
            ms["base_slippage"] = _tick
            ms["slip_mode"] = "tick"
        else:
            ms = dict(ms)
            ms["slip_mode"] = "legacy"
        slippage = ms["slippage"]
        fill_price = ms["fill_price"]''',
        "cap+slippage",
    ),
    (
        '''        self.today_buys[code] = self.today_buys.get(code, 0) + shares''',
        '''        self.today_buys[code] = self.today_buys.get(code, 0) + shares
        self._open_count = getattr(self, "_open_count", 0) + 1   # 2026-10-01 单日开仓计数''',
        "open-count",
    ),
    (
        '''            "ac_impact_pct": round(ms.get("ac_impact", 0) * 100, 4),''',
        '''            "ac_impact_pct": round(ms.get("ac_impact", 0) * 100, 4),
            "slip_mode": ms.get("slip_mode", "?"),        # 2026-10-01: 滑点口径留痕(tick/legacy)''',
        "slip-mode-field",
    ),
])

print()
print("=" * 80); print("C config.yaml / config.example.yaml 新增旋钮"); print("=" * 80)
apply("config.yaml", [
    (
        "execution:\n  commission: 0.0003",
        "execution:\n"
        "  # ⭐ 2026-10-01 月度复盘新增(均有实测支撑)\n"
        "  # 单日开仓笔数上限(0=不限): 当天第1笔 +0.22%/笔, 第2笔 -2.48%/笔, 第3笔及以后 -2.41%/笔\n"
        "  max_opens_per_day: 2\n"
        "  # 滑点口径: tick=按1跳(0.01/价)校准(实测单笔仅占成交额0.001%, 冲击可忽略) | legacy=旧口径\n"
        "  #   ⚠️ 改口径后, 新成交的 P&L 与历史不可直接比(每笔交易记录带 slip_mode 可区分)\n"
        "  slippage_mode: tick\n"
        "  commission: 0.0003",
        "execution-knobs",
    ),
], must_compile=False)
apply("config.example.yaml", [
    (
        "execution:\n  commission: 0.0003",
        "execution:\n"
        "  # 单日开仓笔数上限(0=不限). 2026-10-01 实测: 当天第1笔 +0.22%/笔(胜率38%),\n"
        "  #   第2笔 -2.48%/笔、第3笔及以后 -2.41%/笔(胜率22~24%) → 默认 2\n"
        "  max_opens_per_day: 2\n"
        "  # 滑点口径: tick(默认, 1跳校准) | legacy(旧口径)\n"
        "  #   实测单笔占当日成交额中位 0.0010% → 冲击可忽略; 真实≈1跳 0.047%/边 vs 旧口径 0.272%/边\n"
        "  slippage_mode: tick\n"
        "  commission: 0.0003",
        "example-knobs",
    ),
], must_compile=False)
print()
print("备份:", BAK)
