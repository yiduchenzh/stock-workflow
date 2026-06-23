content = open(r'D:\Hermes Agent CN Desktop\stock-workflow\core\engine.py', 'r', encoding='utf-8').read()
# Fix the escaped single quotes - replace \' with ' inside f-strings
content = content.replace("ca[\\'type\\']", "ca['type']")
content = content.replace("ca[\\'code\\']", "ca['code']")
content = content.replace("ca[\\'reason\\']", "ca['reason']")
open(r'D:\Hermes Agent CN Desktop\stock-workflow\core\engine.py', 'w', encoding='utf-8').write(content)
print('Fixed escaped quotes in engine.py')

# Verify
content2 = open(r'D:\Hermes Agent CN Desktop\stock-workflow\core\engine.py', 'r', encoding='utf-8').read()
idx = content2.find('ca[')
if idx >= 0:
    print(f'Line around ca[: {content2[idx:idx+70]}')
