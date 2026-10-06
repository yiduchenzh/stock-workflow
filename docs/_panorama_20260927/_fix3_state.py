import json
from pathlib import Path

DATA = Path(r"D:\Hermes Agent CN Desktop\stock-workflow\data")

# ① market_memory.json: GBK → UTF-8（保数据，重编码）
p = DATA / "market_memory.json"
raw = p.read_bytes()
try:
    raw.decode("utf-8")
    print("① market_memory.json 已是 UTF-8，无需转换")
except UnicodeDecodeError:
    d = json.loads(raw.decode("gbk"))
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    ok = json.loads(p.read_text(encoding="utf-8"))
    print("① 已重编码为 UTF-8：%d bytes → %d bytes | 可解析=%s | snapshots=%d"
          % (len(raw), p.stat().st_size, bool(ok), len(ok.get("daily_snapshots", []))))

# ② 清理 pytest 遗留的隔离账户文件（测试产物，非生产账户）
for name in ("sim_state_test.json", "sim_trades_test.json"):
    q = DATA / name
    if q.exists():
        q.unlink()
        print("② 删除遗留测试账户:", name)
    else:
        print("② 不存在(已清):", name)

print("③ 生产账户文件保持不动:", (DATA / "sim_state.json").exists(), (DATA / "sim_trades.json").exists())
