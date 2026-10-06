# -*- coding: utf-8 -*-
"""Enumerate ALL episodes of a douyin mix(合集) via in-page fetch."""
import json
import os
import sys
import time

import requests
import websocket

CDP = "http://127.0.0.1:9222"
OUTDIR = "data/douyin/peihongchuan"

TPL = ("https://www.douyin.com/aweme/v1/web/mix/aweme/?device_platform=webapp&aid=6383"
       "&channel=channel_pc_web&mix_id={mix}&cursor={cur}&count=20"
       "&update_version_code=170400&pc_client_type=1&pc_libra_divert=Windows"
       "&support_h265=0&support_dash=1&version_code=170400&version_name=17.4.0"
       "&cookie_enabled=true&screen_width=1920&screen_height=1080&browser_language=zh-CN"
       "&browser_platform=Win32&browser_name=Edge&browser_online=true&engine_name=Blink")

FETCH_EX = r"""(async function(u){ try { const r = await fetch(u, {credentials:'include'}); const t = await r.text(); return t; } catch(e){ return 'ERR:'+e; } })($URL$)"""


class Cdp:
    def __init__(self, ws):
        self.ws = websocket.create_connection(ws, timeout=180, suppress_origin=True)
        self.i = 0

    def send(self, method, params=None):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params or {}}))
        dl = time.time() + 90
        while time.time() < dl:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.i:
                return m
        raise RuntimeError("cdp timeout")

    def eval(self, expr):
        r = self.send("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True, "awaitPromise": True})
        return ((r.get("result") or {}).get("result") or {}).get("value")


tabs = [t for t in requests.get(CDP + "/json/list", timeout=20).json()
        if (t.get("type") or "") == "page"]
tab = next((t for t in tabs if "douyin.com" in (t.get("url") or "")), tabs[0])
c = Cdp(tab["webSocketDebuggerUrl"])
c.send("Runtime.enable")

mix_ids = json.load(open(os.path.join(OUTDIR, "_mix_ids.json"), encoding="utf-8"))
all_eps = {}
for name, mix in mix_ids.items():
    eps = []
    cur = 0
    for _ in range(6):
        u = TPL.format(mix=mix, cur=cur)
        raw = c.eval(FETCH_EX.replace("$URL$", json.dumps(u)))
        if not raw or raw.startswith("ERR"):
            print(name, "ERR", str(raw)[:120])
            break
        try:
            d = json.loads(raw)
        except Exception:
            print(name, "bad json", raw[:200])
            break
        if d.get("status_code") != 0:
            print(name, "status", d.get("status_code"), raw[:200])
            break
        lst = d.get("aweme_list") or []
        eps.extend([{"aweme_id": a.get("aweme_id"), "desc": a.get("desc"),
                     "duration_s": round(((a.get("video") or {}).get("duration") or 0) / 1000, 1)}
                    for a in lst])
        print("  %s cursor=%s -> %d items, has_more=%s" % (name, cur, len(lst), d.get("has_more")))
        if not d.get("has_more") or not lst:
            break
        cur = d.get("cursor")
        time.sleep(1.5)
    all_eps[name] = eps
    print("%s TOTAL %d" % (name, len(eps)))

json.dump(all_eps, open(os.path.join(OUTDIR, "_mix_episodes.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
for name, eps in all_eps.items():
    print("\n===", name, len(eps))
    for i, e in enumerate(eps, 1):
        print("  第%-3d %s %ss  %s" % (i, e["aweme_id"], e["duration_s"], (e["desc"] or "")[:50]))
