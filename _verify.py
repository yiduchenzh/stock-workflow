import ast, os
base = "D:\\Hermes Agent CN Desktop\\stock-workflow"

files = [
    "executor/base.py",
    "executor/ht_bridge_worker.py",
    "risk/controls.py",
    "risk/position_scaling.py",
    "strategies/chan_theory.py",
    "strategies/intraday_t0.py",
    "strategies/reflexivity.py",
    "strategies/scoring.py",
    "core/engine.py",
    "tests/test_risk.py",
]
all_ok = True
for f in files:
    p = os.path.join(base, f)
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            ast.parse(fh.read())
        print(f"OK  {f}")
    except SyntaxError as e:
        all_ok = False
        print(f"ERR {f}: {e}")

print()
checks = [
    ("executor/base.py", "def buy(self, _code"),
    ("executor/base.py", "def sell(self, _code"),
    ("executor/ht_bridge_worker.py", "result = _do_cancel()"),
    ("executor/ht_bridge_worker.py", "def _do_cancel():"),
    ("risk/controls.py", "def check_all(plans: list, cfg: dict)"),
    ("risk/position_scaling.py", "def check_add_position(pos: dict, current_price: float, kline_df=None) -> dict:"),
    ("risk/position_scaling.py", "def calc_dynamic_position(_capital:"),
    ("strategies/chan_theory.py", "def _classify_bs_points(_tops, _bottoms, _close, df):"),
    ("strategies/chan_theory.py", "def _simulate_mid_level(df, _ratio=4):"),
    ("strategies/intraday_t0.py", "def _t0_grid(_kline, price, cost):"),
    ("strategies/intraday_t0.py", "def _t0_mean_reversion(kline, price, _cost):"),
    ("strategies/reflexivity.py", "def analyze_reflexivity(market_score: float, regime: str, _breadth_data: dict = None) -> dict:"),
    ("strategies/scoring.py", "def _calc_volume_score(kline_df, _analysis):"),
    ("core/engine.py", "check_all(self.plans, self.cfg)"),
]

all_pass = True
for fname, expected in checks:
    p = os.path.join(base, fname)
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    if expected not in content:
        all_pass = False
        print(f"MISS {fname}: {expected}")
    else:
        print(f"OK  {fname}: {expected}")

if all_ok and all_pass:
    print()
    print("ALL VERIFICATIONS PASSED")
else:
    print()
    print("SOME CHECKS FAILED")
