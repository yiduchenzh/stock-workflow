content = open(r'D:\Hermes Agent CN Desktop\stock-workflow\core\engine.py', 'r', encoding='utf-8').read()

idx = content.find('self.alerts.extend(alerts)')
end_idx = content.find('    def step_evaluate', idx)
old_text = content[idx:end_idx]

# Build the new text
new_text = """self.alerts.extend(alerts)
        # Act on position alerts (paper mode: log clearly)
        for a in alerts:
            atype = a["type"]
            if atype == "breach_stop":
                self.log.warning(
                    f"  [SELL] {a['code']}: trailing stop breached "
                    f"price={a['price']:.3f} stop={a['trailing_stop']:.3f} "
                    f"profit={a['profit_pct']:+.1f}%"
                )
            elif atype == "scale_out":
                self.log.info(
                    f"  [SELL] {a['code']}: scale out {a['shares_to_sell']} shares "
                    f"at ~{a['price']:.3f} profit={a['profit_pct']:+.1f}%"
                )
            elif atype == "trailing_stop":
                self.log.info(
                    f"  [INFO] {a['code']}: trailing stop raised to {a['trailing_stop']:.4f} "
                    f"profit={a['profit_pct']:+.1f}%"
                )
            elif atype == "stop_loss":
                self.log.warning(
                    f"  [SELL] {a['code']}: hard stop loss "
                    f"price={a['price']:.3f} stop={a['stop']:.3f}"
                )
            elif atype == "take_profit":
                self.log.info(
                    f"  [SELL] {a['code']}: take profit "
                    f"price={a['price']:.3f} target={a['target']:.3f}"
                )
        # """ + content[idx:].split("# ")[1]  # grab the contingency comment

# Actually let me just keep the exact same contingency block
rest_of_file = content[end_idx:]
# Re-extract the contingency block portion
contingency_start = content.find("# \xe7\x9b\x98\xe4\xb8\xad\xe7\xaa\x81\xe5\x8f\x91\xe6\xa3\x80\xe6\x9f\xa5", idx)
if contingency_start == -1:
    contingency_start = old_text.find("# ")

new_body = (
    "self.alerts.extend(alerts)\n"
    "        # Act on position alerts (paper mode: log clearly)\n"
    '        for a in alerts:\n'
    '            atype = a["type"]\n'
    '            if atype == "breach_stop":\n'
    '                self.log.warning(\n'
    "                    f\"  [SELL] {a['code']}: trailing stop breached \"\n"
    "                    f\"price={a['price']:.3f} stop={a['trailing_stop']:.3f} \"\n"
    "                    f\"profit={a['profit_pct']:+.1f}%\"\n"
    '                )\n'
    '            elif atype == "scale_out":\n'
    '                self.log.info(\n'
    "                    f\"  [SELL] {a['code']}: scale out {a['shares_to_sell']} shares \"\n"
    "                    f\"at ~{a['price']:.3f} profit={a['profit_pct']:+.1f}%\"\n"
    '                )\n'
    '            elif atype == "trailing_stop":\n'
    '                self.log.info(\n'
    "                    f\"  [INFO] {a['code']}: trailing stop raised to {a['trailing_stop']:.4f} \"\n"
    "                    f\"profit={a['profit_pct']:+.1f}%\"\n"
    '                )\n'
    '            elif atype == "stop_loss":\n'
    '                self.log.warning(\n'
    "                    f\"  [SELL] {a['code']}: hard stop loss \"\n"
    "                    f\"price={a['price']:.3f} stop={a['stop']:.3f}\"\n"
    '                )\n'
    '            elif atype == "take_profit":\n'
    '                self.log.info(\n'
    "                    f\"  [SELL] {a['code']}: take profit \"\n"
    "                    f\"price={a['price']:.3f} target={a['target']:.3f}\"\n"
    '                )\n'
    "        # \xe7\x9b\x98\xe4\xb8\xad\xe7\xaa\x81\xe5\x8f\x91\xe6\xa3\x80\xe6\x9f\xa5\n"
    "        from monitor.contingency import check_contingency\n"
    '        market_status = {"index_change": 0}  # \xe7\xae\x80\xe5\x8c\x96: \xe6\x97\xa5\xe7\xba\xbf\xe7\xba\xa7\xe5\x88\xab\xe6\x97\xa0\xe6\xb3\x95\xe8\x8e\xb7\xe5\x8f\x96\xe7\x9b\x98\xe4\xb8\xad\xe5\xa4\xa7\xe7\x9b\x98\xe6\xb6\xa8\xe8\xb7\x8c\n'
    "        kline_cache = {}\n"
    "        for code in self.positions:\n"
    "            from data.sources import get_kline\n"
    "            df = get_kline(code, 30)\n"
    "            if not df.empty: kline_cache[code] = df\n"
    "        contingency_alerts = check_contingency(self.positions, market_status, kline_cache)\n"
    "        if contingency_alerts:\n"
    "            self.alerts.extend(contingency_alerts)\n"
    "            for ca in contingency_alerts:\n"
    '                self.log.warning(f"  [ALERT] {ca[\\\'type\\\']}: {ca[\\\'code\\\']} {ca[\\\'reason\\\']}")\n'
)

print(f'old_text found: {old_text in content}')
content = content.replace(old_text, new_body)
open(r'D:\Hermes Agent CN Desktop\stock-workflow\core\engine.py', 'w', encoding='utf-8').write(content)
print('SUCCESS: engine.py updated')
