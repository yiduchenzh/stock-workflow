# -*- coding: utf-8 -*-
"""深挖 trades.json 读取失败的真实异常"""
import sys, json, traceback
sys.path.insert(0, '.')
from pathlib import Path

ROOT = Path(r"D:\Hermes Agent CN Desktop\stock-workflow")
trades_file = ROOT / "data" / "agent_短线狙击手" / "trades.json"

raw = trades_file.read_bytes()
print(f"文件大小: {len(raw)}B, 前3字节: {raw[:3]}")
print(f"GBK解码: {raw.decode('gbk', errors='replace')[:200]}")
print()

# 复现 Path.read_text() 默认编码行为
print("Path.read_text() 默认: ", end="")
try:
    t = trades_file.read_text()
    print(f"OK {len(json.loads(t))}条 (编码={trades_file.read_text(encoding='utf-8') is not None})")
except Exception as e:
    print(f"失败: {type(e).__name__}: {e}")

print("Path.read_text(utf-8): ", end="")
try:
    t = trades_file.read_text(encoding="utf-8")
    print(f"OK {len(json.loads(t))}条")
except Exception as e:
    print(f"失败: {type(e).__name__}: {e}")

print("Path.read_text(gbk): ", end="")
try:
    t = trades_file.read_text(encoding="gbk")
    print(f"OK {len(json.loads(t))}条")
except Exception as e:
    print(f"失败: {type(e).__name__}: {e}")

# 关键: json.loads 对 GBK 内容
print()
print("json.loads(gbk_text): ", end="")
try:
    t = trades_file.read_text(encoding="gbk")
    d = json.loads(t)
    print(f"OK {len(d)}条")
except Exception as e:
    print(f"失败: {type(e).__name__}: {e}")
    traceback.print_exc()

# 检查 _load 的实现是否用 read_text() 无 encoding
print()
print("=== SimAccount._load 源码 ===")
from executor import sim_account
import inspect
src = inspect.getsource(sim_account.SimAccount._load)
print(src)
