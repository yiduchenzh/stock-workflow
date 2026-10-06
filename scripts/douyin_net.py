# -*- coding: utf-8 -*-
"""Capture douyin XHR URLs on a video page to find the mix(合集) API + mix_id."""
import json
import sys
import time

import requests
import websocket

CDP = "http://127.0.0.1:9222"
url = sys.argv[1]


class Cdp:
    def __init__(self, ws):
        self.ws = websocket.create_connection(ws, timeout=120, suppress_origin=True)
        self.i = 0

    def send(self, method, params=None):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params or {}}))
        dl = time.time() + 60
        while time.time() < dl:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.i:
                return m
        raise RuntimeError("cdp timeout")

    def drain(self, seconds):
        end = time.time() + seconds
        self.ws.settimeout(2)
        msgs = []
        while time.time() < end:
            try:
                msgs.append(json.loads(self.ws.recv()))
            except Exception:
                pass
        self.ws.settimeout(120)
        return msgs


tabs = [t for t in requests.get(CDP + "/json/list", timeout=20).json()
        if (t.get("type") or "") == "page"]
tab = next((t for t in tabs if "douyin.com" in (t.get("url") or "")), tabs[0])
c = Cdp(tab["webSocketDebuggerUrl"])
c.send("Page.enable")
c.send("Runtime.enable")
c.send("Network.enable")
c.send("Page.navigate", {"url": url})
msgs = c.drain(20)

reqs = {}
for m in msgs:
    if m.get("method") == "Network.responseReceived":
        p = m["params"]
        reqs[p["requestId"]] = {"url": p["response"]["url"], "status": p["response"]["status"]}

print("captured %d responses" % len(reqs))
hits = {k: v for k, v in reqs.items() if any(w in v["url"].lower()
        for w in ("mix", "collection", "series", "playlist"))}
print("\nMIX/COLLECTION HITS: %d" % len(hits))
for k, v in list(hits.items())[:20]:
    print("  ", v["status"], v["url"][:220])

print("\nALL API URLs (top 40):")
for k, v in list(reqs.items())[:400]:
    u = v["url"]
    if "/aweme/v1/" in u or "/web/" in u:
        print("  ", v["status"], u[:200])
