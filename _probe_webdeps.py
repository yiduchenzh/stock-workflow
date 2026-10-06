"""临时探针：检查当前解释器的浏览器/抓取相关依赖是否可用。用完即删。"""
import importlib.util as u
import sys

MODS = ["playwright", "selenium", "requests", "bs4", "pandas", "lxml", "httpx", "pyppeteer", "curl_cffi"]
print("interpreter:", sys.executable)
for m in MODS:
    try:
        ok = bool(u.find_spec(m))
    except Exception:
        ok = False
    print(f"  {m}: {ok}")
