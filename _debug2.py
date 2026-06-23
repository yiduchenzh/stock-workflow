import sys
content = open(r'D:\Hermes Agent CN Desktop\stock-workflow\core\engine.py', 'r', encoding='utf-8').read()
old = (
    '        self.alerts.extend(alerts)\n'
    '        # \xe7\x9b\x98\xe4\xb8\xad\xe7\xaa\x81\xe5\x8f\x91\xe6\xa3\x80\xe6\x9f\xa5\n'
    '        from monitor.contingency import check_contingency\n'
    '        market_status = {"index_change": 0}  # \xe7\xae\x80\xe5\x8c\x96: \xe6\x97\xa5\xe7\xba\xbf\xe7\xba\xa7\xe5\x88\xab\xe6\x97\xa0\xe6\xb3\x95\xe8\x8e\xb7\xe5\x8f\x96\xe7\x9b\x98\xe4\xb8\xad\xe5\xa4\xa7\xe7\x9b\x98\xe6\xb6\xa8\xe8\xb7\x8c\n'
    '        kline_cache = {}\n'
    '        for code in self.positions:\n'
    '            from data.sources import get_kline\n'
    '            df = get_kline(code, 30)\n'
    '            if not df.empty: kline_cache[code] = df\n'
    '        contingency_alerts = check_contingency(self.positions, market_status, kline_cache)\n'
    '        if contingency_alerts:\n'
    '            self.alerts.extend(contingency_alerts)\n'
    '            for ca in contingency_alerts:\n'
    '                self.log.warning(f"  [ALERT] {ca[chr(39)+chr(116)+chr(121)+chr(112)+chr(101)+chr(39)]}: {ca[chr(39)+chr(99)+chr(111)+chr(100)+chr(101)+chr(39)]} {ca[chr(39)+chr(114)+chr(101)+chr(97)+chr(115)+chr(111)+chr(110)+chr(39)]}")'
)
print(f'In content: {old in content}')
if old in content:
    print('old text found')
else:
    idx = content.find('self.alerts.extend(alerts)')
    if idx >= 0:
        print(f'Found at {idx}')
        region = content[idx:idx+len(old)]
        print(f'Length match: {len(region)} vs {len(old)}')
        for i, (a, b) in enumerate(zip(region, old)):
            if a != b:
                print(f'Diff at {i}: got {repr(a)} ({ord(a)}) expected {repr(b)} ({ord(b)})')
                if i > 10:
                    print(f'Context region: {repr(region[max(0,i-10):i+20])}')
                break
        else:
            print('No differences found in zip - may be encoding')
