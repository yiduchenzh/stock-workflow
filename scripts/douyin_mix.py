# -*- coding: utf-8 -*-
"""Capture douyin mix(合集) API response bodies -> enumerate all episodes."""
import json
import os
import sys
import time
import urllib.parse

import requests
import websocket

CDP = "http://127.0.0.1:9222"
url = sys.argv[1]
outdir = "data/douyin/peihongchuan"
os.makedirs(outdir, exist_ok=True)


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
msgs = c.drain(22)

targets = {}
for m in msgs:
    if m.get("method") == "Network.responseReceived":
        p = m["params"]
        u = p["response"]["url"]
        if "/web/mix/aweme/" in u or "/web/mix/listcollection/" in u or "/web/aweme/detail/" in u:
            targets[p["requestId"]] = u

print("targets:", len(targets))
saved = 0
for rid, u in targets.items():
    try:
        r = c.send("Network.getResponseBody", {"requestId": rid})
        body = (r.get("result") or {}).get("body")
        if not body:
            continue
        if (r.get("result") or {}).get("base64Encoded"):
            import base64
            body = base64.b64decode(body).decode("utf-8", "ignore")
        tag = "mix_aweme" if "/mix/aweme/" in u else ("mix_list" if "/mix/listcollection/" in u else "aweme_detail")
        q = urllib.parse.urlparse(u).query
        mixid = urllib.parse.parse_qs(q).get("mix_id", [""])[0]
        cur = urllib.parse.parse_qs(q).get("cursor", [""])[0]
        fn = "%s/_%s_%s_%s.json" % (outdir, tag, mixid, cur)
        json.dump(json.loads(body), open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("  saved", fn, len(body), "bytes")
        saved += 1
    except Exception as e:
        print("  body err:", str(e)[:80])
print("done", saved)
