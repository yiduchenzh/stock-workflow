import json
import sys
sys.path.insert(0, r"D:\Hermes Agent CN Desktop\hunter-v2\backend")

from data_service import PUSH2, GLOBAL_INDICES_MAP  # noqa
print("PUSH2 =", PUSH2)
print("指数表 =", GLOBAL_INDICES_MAP[:3], "...")

import em_node

name, secid = GLOBAL_INDICES_MAP[0]
qs = "secid=%s&fields=f43,f170,f57,f58" % secid

print("\n=== ① em_node 直接调用【无 params】(main.py 补丁走的就是这条) ===")
try:
    d = em_node.get_json(PUSH2)          # 补丁传的就是这个——没有 query
    print("   返回:", json.dumps(d, ensure_ascii=False)[:200])
    data = d.get("data") or {}
    print("   f43 =", data.get("f43"), "→ price =", (data.get("f43") or 0) / 100.0)
except Exception as e:
    print("   异常:", type(e).__name__, e)

print("\n=== ② em_node 调用【带正确 query】 ===")
try:
    d = em_node.get_json(PUSH2 + "/api/qt/stock/get?" + qs)
    data = d.get("data") or {}
    print("   返回:", json.dumps(d, ensure_ascii=False)[:220])
    print("   f43 =", data.get("f43"), "→ price =", (data.get("f43") or 0) / 100.0,
          "| f170 =", data.get("f170"), "→ chg% =", (data.get("f170") or 0) / 100.0)
except Exception as e:
    print("   异常:", type(e).__name__, e)

print("\n=== ③ 正常 httpx（绕过 em_node，看东财本机是否直连可用） ===")
try:
    import httpx
    r = httpx.Client(timeout=8).get(PUSH2 + "/api/qt/stock/get", params={"secid": secid,
                                                                        "fields": "f43,f170,f57,f58"})
    print("   HTTP", r.status_code, "| 返回:", r.text[:200])
except Exception as e:
    print("   异常:", type(e).__name__, str(e)[:160])
