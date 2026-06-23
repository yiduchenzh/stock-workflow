import ast
path = "D:\\Hermes Agent CN Desktop\\stock-workflow\\executor\\ht_bridge_worker.py"
with open(path, "rb") as f:
    raw = f.read()
if raw[:3] == b"\xef\xbb\xbf":
    raw = raw[3:]
    with open(path, "wb") as f:
        f.write(raw)
    print("BOM stripped")
else:
    print("No BOM found")

with open(path, "r", encoding="utf-8") as f:
    ast.parse(f.read())
print("Syntax OK")
