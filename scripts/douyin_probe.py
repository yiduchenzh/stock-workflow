# -*- coding: utf-8 -*-
"""Probe a douyin page: dump visible text + all video/user anchors.

Usage: python scripts/douyin_probe.py "<url>" [out.json]
"""
import json
import os
import subprocess
import sys
import time

import requests
import websocket

CDP = "http://127.0.0.1:9222"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
UD = r"C:\Users\User871619\AppData\Local\Temp\edge-cdp3"

VEX = r"""JSON.stringify({
  title: document.title,
  url: location.href,
  text: (document.body ? document.body.innerText : '').replace(/\s+/g,' ').slice(0, 8000),
  anchors: Array.from(document.querySelectorAll('a')).map(a => a.getAttribute('href')).filter(Boolean).slice(0, 400)
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
    if not os.path.exists(EDGE):
        print("EDGE NOT FOUND:", EDGE, flush=True)
        return False
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


def connect(hint="douyin.com"):
    tabs = requests.get(CDP + "/json/list", timeout=20).json()
    tab = next((t for t in tabs if hint in (t.get("url") or "")), None)
    if not tab:
        tab = requests.put(CDP + "/json/new?about:blank", timeout=25).json()
        time.sleep(2)
    c = Cdp(tab["webSocketDebuggerUrl"])
    c.send("Page.enable")
    c.send("Runtime.enable")
    return c


def main():
    url = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "data/douyin_probe.json"
    if not ensure_edge():
        return 1
    c = connect()
    for attempt in (1, 2, 3):
        try:
            c.send("Page.navigate", {"url": url})
            time.sleep(12)
            d = json.loads(c.eval(VEX) or "{}")
            if d.get("text"):
                break
        except Exception as e:
            print("attempt %d fail: %s" % (attempt, str(e)[:80]), flush=True)
            try:
                c.close()
            except Exception:
                pass
            time.sleep(8)
            c = connect()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    json.dump(d, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("title:", d.get("title"))
    print("url:", d.get("url"))
    print("text(%d):" % len(d.get("text") or ""), (d.get("text") or "")[:1500])
    anchors = d.get("anchors") or []
    vids = sorted(set(a for a in anchors if "/video/" in a))
    users = sorted(set(a for a in anchors if "/user/" in a))
    print("\nANCHORS total=%d video=%d user=%d" % (len(anchors), len(vids), len(users)))
    for u in users[:20]:
        print("  USER", u)
    for v in vids[:20]:
        print("  VID ", v)
    print("\nsaved ->", out_path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
