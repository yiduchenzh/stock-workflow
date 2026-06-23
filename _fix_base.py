path = "D:\\Hermes Agent CN Desktop\\stock-workflow\\executor\\base.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    '    def buy(self, code: str, price: float, shares: int, reason: str = "") -> dict:',
    '    def buy(self, _code: str, _price: float, _shares: int, _reason: str = "") -> dict:'
)
content = content.replace(
    '    def sell(self, code: str, price: float, shares: int, reason: str = "") -> dict:',
    '    def sell(self, _code: str, _price: float, _shares: int, _reason: str = "") -> dict:'
)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

with open(path) as f:
    c2 = f.read()
assert "def buy(self, _code" in c2
assert "def sell(self, _code" in c2
print("base.py done")
