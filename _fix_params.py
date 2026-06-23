import re

# === 1. executor/ht_bridge_worker.py ===
path = 'D:\\Hermes Agent CN Desktop\\stock-workflow\\executor\\ht_bridge_worker.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('result = _do_cancel(cmd)', 'result = _do_cancel()')
content = content.replace('def _do_cancel(cmd):', 'def _do_cancel():')
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('1. ht_bridge_worker.py done')

# === 2. risk/controls.py ===
path = 'D:\\Hermes Agent CN Desktop\\stock-workflow\\risk\\controls.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('def check_all(plans: list, positions: dict, cfg: dict) -> tuple:', 'def check_all(plans: list, cfg: dict) -> tuple:')
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('2. controls.py done')

# === 3. core/engine.py ===
path = 'D:\\Hermes Agent CN Desktop\\stock-workflow\\core\\engine.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('self.plans, self.alerts = check_all(self.plans, self.positions, self.cfg)', 'self.plans, self.alerts = check_all(self.plans, self.cfg)')
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('3. engine.py done')

# === 4. tests/test_risk.py ===
path = 'D:\\Hermes Agent CN Desktop\\stock-workflow\\tests\\test_risk.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
content = re.sub(r'check_all\((\[[^\]]*\]),\s*\{\},\s*(\{[^}]*\})\)', r'check_all(\1, \2)', content)
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('4. test_risk.py done')

# === 5. risk/position_scaling.py ===
path = 'D:\\Hermes Agent CN Desktop\\stock-workflow\\risk\\position_scaling.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('def check_add_position(pos: dict, current_price: float, kline_df=None, cfg: dict = None) -> dict:', 'def check_add_position(pos: dict, current_price: float, kline_df=None) -> dict:')
content = content.replace('def calc_dynamic_position(capital: float, score: float, confidence: float,', 'def calc_dynamic_position(_capital: float, score: float, confidence: float,')
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('5. position_scaling.py done')

# === 6. strategies/chan_theory.py ===
path = 'D:\\Hermes Agent CN Desktop\\stock-workflow\\strategies\\chan_theory.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('def _classify_bs_points(tops, bottoms, close, df):', 'def _classify_bs_points(_tops, _bottoms, _close, df):')
content = content.replace('def _simulate_mid_level(df, ratio=4):', 'def _simulate_mid_level(df, _ratio=4):')
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('6. chan_theory.py done')

# === 7. strategies/intraday_t0.py ===
path = 'D:\\Hermes Agent CN Desktop\\stock-workflow\\strategies\\intraday_t0.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('def _t0_grid(kline, price, cost):', 'def _t0_grid(_kline, price, cost):')
content = content.replace('def _t0_mean_reversion(kline, price, cost):', 'def _t0_mean_reversion(kline, price, _cost):')
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('7. intraday_t0.py done')

# === 8. strategies/reflexivity.py ===
path = 'D:\\Hermes Agent CN Desktop\\stock-workflow\\strategies\\reflexivity.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('def analyze_reflexivity(market_score: float, regime: str, breadth_data: dict = None) -> dict:', 'def analyze_reflexivity(market_score: float, regime: str, _breadth_data: dict = None) -> dict:')
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('8. reflexivity.py done')

# === 9. strategies/scoring.py ===
path = 'D:\\Hermes Agent CN Desktop\\stock-workflow\\strategies\\scoring.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('def _calc_volume_score(kline_df, analysis):', 'def _calc_volume_score(kline_df, _analysis):')
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('9. scoring.py done')

print('\nAll fixes applied!')
