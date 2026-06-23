import sys
content = open(r'D:\Hermes Agent CN Desktop\stock-workflow\core\engine.py', 'r', encoding='utf-8').read()
idx = content.find('self.alerts.extend(alerts)')
# Find the full old text from right before self.alerts to the start of next method
end_idx = content.find('    def step_evaluate', idx)
old_text = content[idx:end_idx]
print(f'old_text length: {len(old_text)}')
print(repr(old_text[:300]))
print('...')
print(repr(old_text[-300:]))
