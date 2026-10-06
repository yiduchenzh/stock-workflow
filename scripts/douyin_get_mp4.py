# -*- coding: utf-8 -*-
"""Capture real mp4 play URLs for each douyin video via the aweme/detail XHR."""
import json
import os
import sys
import time

import requests
import websocket

CDP = "http://127.0.0.1:9222"
OUTDIR = "data/douyin/peihongchuan"
DETAILS = os.path.join(OUTDIR, "video_details.json")


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

    def drain(self, seconds):
        end = time.time() + seconds
        self.ws.settimeout(2)
        msgs = []
        while time.time() < end:
            try:
                msgs.append(json.loads(self.ws.recv()))
            except Exception:
                pass
        self.ws.settimeout(180)
        return msgs

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def connect():
    tabs = [t for t in requests.get(CDP + "/json/list", timeout=20).json()
            if (t.get("type") or "") == "page"]
    tab = next((t for t in tabs if "douyin.com" in (t.get("url") or "")), tabs[0])
    c = Cdp(tab["webSocketDebuggerUrl"])
    c.send("Page.enable")
    c.send("Runtime.enable")
    c.send("Network.enable")
    return c


def candidates(detail):
    """All playable variants, largest first (full-quality ones carry audio)."""
    ad = (detail or {}).get("aweme_detail") or {}
    v = ad.get("video") or {}
    out = []
    for br in (v.get("bit_rate") or []):
        pa = br.get("play_addr") or {}
        for u in (pa.get("url_list") or []):
            out.append({"size": pa.get("data_size") or 0, "gear": br.get("gear_name"),
                        "h265": br.get("is_h265"), "fmt": br.get("format"), "url": u})
    pa = v.get("play_addr") or {}
    for u in (pa.get("url_list") or []):
        out.append({"size": pa.get("data_size") or 0, "gear": "play_addr",
                    "h265": None, "fmt": None, "url": u})
    out.sort(key=lambda x: -x["size"])
    return out


def best_url(detail):
    c = candidates(detail)
    return c[0]["url"] if c else None


details = json.load(open(DETAILS, encoding="utf-8"))
todo = [h for h, v in details.items() if not v.get("cands")]
print("todo=%d / %d" % (len(todo), len(details)), flush=True)

c = connect()
for n, href in enumerate(todo, 1):
    ok = False
    for attempt in (1, 2):
        try:
            msgs = []
            c.send("Page.navigate", {"url": href})
            msgs = c.drain(16)
            rid = None
            for m in msgs:
                if m.get("method") == "Network.responseReceived":
                    u = m["params"]["response"]["url"]
                    if "/aweme/v1/web/aweme/detail/" in u:
                        rid = m["params"]["requestId"]
            if not rid:
                raise RuntimeError("no detail xhr")
            r = c.send("Network.getResponseBody", {"requestId": rid})
            body = (r.get("result") or {}).get("body")
            if (r.get("result") or {}).get("base64Encoded"):
                import base64
                body = base64.b64decode(body).decode("utf-8", "ignore")
            d = json.loads(body)
            cs = candidates(d)
            u = cs[0]["url"] if cs else None
            if not u:
                raise RuntimeError("no play_addr")
            details[href]["src"] = u
            details[href]["cands"] = cs
            tmp = DETAILS + ".tmp"
            json.dump(details, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            os.replace(tmp, DETAILS)
            ok = True
            print("[%2d/%2d] OK %s ...%s" % (n, len(todo), href[-19:], u[-40:]), flush=True)
            break
        except Exception as e:
            print("[%2d/%2d] try%d FAIL %s" % (n, len(todo), attempt, str(e)[:70]), flush=True)
            try:
                c.close()
            except Exception:
                pass
            time.sleep(4)
            c = connect()
    time.sleep(1)
print("done", flush=True)
