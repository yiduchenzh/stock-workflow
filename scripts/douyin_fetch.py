# -*- coding: utf-8 -*-
"""Self-hosted: launch CDP Edge, then fetch remaining real works' detail pages.

Only the first 18 items in videos.json are the author's real works
(the rest are recommendation-stream noise).
"""
import json
import os
import subprocess
import time

import requests
import websocket

CDP = "http://127.0.0.1:9222"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
UD = r"C:\Users\User871619\AppData\Local\Temp\edge-cdp3"
IN = "data/douyin/videos.json"
OUT = "data/douyin/video_details.json"

VEX = r"""JSON.stringify({
  title: document.title,
  url: location.href,
  text: (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').slice(0, 3500)
})"""


class Cdp:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=90, suppress_origin=True)
        self.i = 0

    def send(self, method, params=None):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params or {}}))
        dl = time.time() + 45
        while time.time() < dl:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.i:
                return m
        raise RuntimeError("cdp timeout")

    def eval(self, expr):
        r = self.send("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True, "awaitPromise": True})
        return ((r.get("result") or {}).get("result") or {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def ensure_edge():
    try:
        requests.get(CDP + "/json/version", timeout=3)
        print("CDP already up", flush=True)
        return True
    except Exception:
        pass
    os.makedirs(UD, exist_ok=True)
    print("launching Edge ...", flush=True)
    subprocess.Popen([EDGE, "--remote-debugging-port=9222", "--user-data-dir=" + UD,
                      "--no-first-run", "--no-default-browser-check", "--disable-sync",
                      "about:blank"],
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                     close_fds=True)
    for i in range(30):
        time.sleep(2)
        try:
            requests.get(CDP + "/json/version", timeout=3)
            print("CDP up after %ds" % ((i + 1) * 2), flush=True)
            return True
        except Exception:
            pass
    print("CDP failed to come up", flush=True)
    return False


def connect(url_hint="douyin.com"):
    tabs = requests.get(CDP + "/json/list", timeout=20).json()
    tab = next((t for t in tabs if url_hint in (t.get("url") or "")), None)
    if not tab:
        tab = requests.put(CDP + "/json/new?about:blank", timeout=25).json()
        time.sleep(3)
    c = Cdp(tab["webSocketDebuggerUrl"])
    c.send("Page.enable")
    c.send("Runtime.enable")
    return c


def main():
    if not ensure_edge():
        return 1
    data = json.load(open(IN, encoding="utf-8"))
    items = (data.get("items") or [])[:18]        # real works only
    out = {}
    if os.path.exists(OUT):
        try:
            out = json.load(open(OUT, encoding="utf-8"))
        except Exception:
            out = {}
    todo = [it for it in items if it.get("href") and it["href"] not in out]
    print("real works=%d cached=%d todo=%d" % (len(items), len(out), len(todo)), flush=True)

    c = connect()
    ok = 0
    for i, it in enumerate(todo):
        href = it["href"]
        for attempt in (1, 2):
            try:
                c.send("Page.navigate", {"url": href})
                time.sleep(10)
                d = json.loads(c.eval(VEX) or "{}")
                if not (d.get("text") or ""):
                    raise RuntimeError("empty")
                d["list_title"] = it.get("title")
                out[href] = d
                ok += 1
                json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                print("[%2d/%2d] OK %s" % (i + 1, len(todo), (d.get("title") or "")[:50]), flush=True)
                break
            except Exception as e:
                print("[%2d/%2d] try%d FAIL %s" % (i + 1, len(todo), attempt, str(e)[:60]), flush=True)
                try:
                    c.close()
                except Exception:
                    pass
                time.sleep(15)
                try:
                    c = connect()
                except Exception as e2:
                    print("   reconnect fail: %s" % str(e2)[:50], flush=True)
        time.sleep(5)
    print("\ndone new=%d cached=%d -> %s" % (ok, len(out), OUT), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
