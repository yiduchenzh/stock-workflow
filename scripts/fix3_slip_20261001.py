# -*- coding: utf-8 -*-
"""修正批次2的滑点实现: 从 buy() 内联改为 _get_micro_slippage 单点校准(买卖双向一致) + 修 is_buy NameError"""
import io
import os
import py_compile
import shutil
from datetime import datetime

ROOT = r"D:\Hermes Agent CN Desktop\stock-workflow"
BAK = os.path.join(ROOT, "_restore", "fix3_20261001_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
os.makedirs(BAK, exist_ok=True)
p = os.path.join(ROOT, "executor", "sim_account.py")
shutil.copy2(p, os.path.join(BAK, "sim_account.py"))
raw = io.open(p, encoding="utf-8", newline="").read()
nl = "\r\n" if "\r\n" in raw else "\n"
src = raw.replace("\r\n", "\n")
print("行尾:", "CRLF" if nl == "\r\n" else "LF")

# ── E1: 移除 buy() 内联的滑点校准块(它在 buy 作用域里引用了未定义的 is_buy) ──
INLINE = '''        ms = self._get_micro_slippage(code, shares, price, is_buy=True)

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
        fill_price = ms["fill_price"]'''
NEW_INLINE = '''        ms = self._get_micro_slippage(code, shares, price, is_buy=True)
        slippage = ms["slippage"]
        fill_price = ms["fill_price"]'''
assert src.count(INLINE) == 1, "E1 锚点 count=%d" % src.count(INLINE)
src = src.replace(INLINE, NEW_INLINE, 1)
print("[OK] E1 buy() 内联校准块已移除")

# ── E2: 在 _get_micro_slippage 里单点校准(双向一致) ──
OLD_MICRO = '''            return self._ms_slippage.compute_slippage(
                shares=shares, price=price, is_buy=is_buy,
                mcap_hundred_million=params["mcap_hundred_million"],
            )'''
NEW_MICRO = '''            return self._apply_slip_mode(self._ms_slippage.compute_slippage(
                shares=shares, price=price, is_buy=is_buy,
                mcap_hundred_million=params["mcap_hundred_million"],
            ), code, shares, price, is_buy)'''
assert src.count(OLD_MICRO) == 1, "E2a 锚点 count=%d" % src.count(OLD_MICRO)
src = src.replace(OLD_MICRO, NEW_MICRO, 1)
print("[OK] E2a 微结构路径接入单点校准")

OLD_FB = '''            slip = base_slip * tf + random.uniform(0, 0.001)
            return {
                "slippage": slip,
                "base_slippage": base_slip,
                "time_factor": tf,
                "ac_impact": 0.0,
                "noise": random.uniform(0, 0.001),
                "fill_price": price * (1 + slip) if is_buy else price * (1 - slip),
                "impact_detail": {},
                "order_type_advice": {},
            }'''
NEW_FB = '''            slip = base_slip * tf + random.uniform(0, 0.001)
            return self._apply_slip_mode({
                "slippage": slip,
                "base_slippage": base_slip,
                "time_factor": tf,
                "ac_impact": 0.0,
                "noise": random.uniform(0, 0.001),
                "fill_price": price * (1 + slip) if is_buy else price * (1 - slip),
                "impact_detail": {},
                "order_type_advice": {},
            }, code, shares, price, is_buy)'''
assert src.count(OLD_FB) == 1, "E2b 锚点 count=%d" % src.count(OLD_FB)
src = src.replace(OLD_FB, NEW_FB, 1)
print("[OK] E2b 回退路径接入单点校准")

# ── E3: 新增 _apply_slip_mode 方法(插在 _get_micro_slippage 之前) ──
ANCHOR3 = '''    def _get_micro_slippage(self, code: str, shares: int, price: float,'''
METHOD = '''    def _apply_slip_mode(self, res: dict, code: str, shares: int, price: float,
                         is_buy: bool) -> dict:
        """⭐ 2026-10-01 滑点口径校准(实测, 月度复盘)

        实测证据(305 笔成交, 对 market.db):
          · 单笔金额占当日成交额 **中位 0.0010%**(90分位 0.0031%) ⇒ 冲击成本可忽略
          · 真实滑点 ≈ 1跳(0.01/价格): 中位 **0.047%/边**, 均值 0.069%/边
          · 旧口径实收 **0.272%/边** ⇒ **高估 5.8 倍**(往返虚增约 0.45%/笔) → 模拟盘低估实盘收益

        mode(execution.slippage_mode): tick(默认) | legacy(旧口径, 与历史 P&L 可比)
        ⚠️ 买卖**同一函数**校准 —— 若只改一侧会变成"买便宜卖贵"的偏袒偏置。
        """
        try:
            c = self.config or {}
            mode = str(c.get("slippage_mode")
                       or (c.get("execution") or {}).get("slippage_mode") or "tick").lower()
        except Exception:
            mode = "tick"
        out = dict(res or {})
        if mode == "legacy" or price <= 0:
            out["slip_mode"] = "legacy"
            return out
        tick = 0.01 / price
        turn = float((self._stock_micro_cache.get(code) or {}).get("avg_daily_turnover") or 5e8)
        part_pct = (shares * price) / turn * 100.0        # 参与度 %
        impact = 0.1 * (part_pct ** 0.5) / 100.0          # 平方根冲击律(1% 参与度 → 0.1%)
        slip = max(tick, min(0.001, impact))
        out["slippage"] = slip
        out["base_slippage"] = tick
        out["fill_price"] = price * (1 + slip) if is_buy else price * (1 - slip)
        out["slip_mode"] = "tick"
        return out

'''
assert src.count(ANCHOR3) == 1, "E3 锚点 count=%d" % src.count(ANCHOR3)
src = src.replace(ANCHOR3, METHOD + ANCHOR3, 1)
print("[OK] E3 新增 _apply_slip_mode")

out = src.replace("\n", nl) if nl == "\r\n" else src
tmp = p + ".chk.py"
io.open(tmp, "w", encoding="utf-8", newline="").write(out)
py_compile.compile(tmp, doraise=True)
os.remove(tmp)
io.open(p, "w", encoding="utf-8", newline="").write(out)
print("[COMPILE-OK] 已写回 (行尾保持 %s)" % ("CRLF" if nl == "\r\n" else "LF"))
print()
print("=== 回读关键区 ===")
chk = io.open(p, encoding="utf-8").read()
i = chk.find("def _apply_slip_mode")
print(chk[i:i + 240])
j = chk.find('        ms = self._get_micro_slippage(code, shares, price, is_buy=True)')
print("...\n" + chk[j:j + 130])
print("备份:", BAK)
