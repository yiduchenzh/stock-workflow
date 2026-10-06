# -*- coding: utf-8 -*-
"""Harvest a douyin user's works list (scoped to the profile "作品" list container).

Usage:
  python scripts/douyin_harvest.py "<user_url>" <outdir>
Writes <outdir>/videos.json and <outdir>/profile.json
"""
import json
import os
import re
import subprocess
import sys
import time

import requests
import websocket

CDP = "http://127.0.0.1:9222"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
UD = r"C:\Users\User871619\AppData\Local\Temp\edge-cdp3"

TEXTEX = r"""JSON.stringify({
  title: document.title,
  url: location.href,
  text: (document.body ? document.body.innerText : '').replace(/\s+/g,' ').slice(0, 20000)
})"""

LIST_SEL = 'div[data-e2e="user-post-list"]'
CARDS_EX = r"""JSON.stringify(
  Array.from(document.querySelectorAll('div[data-e2e="user-post-list"] a[href*="/video/"]')).map(a => {
    var li = a.closest('li') || a.parentElement || a;
    return {
      href: (a.href||'').split('?')[0],
      card: (li.innerText||'').replace(/\s+/g,' ').trim().slice(0,200)
    };
  }).filter(x => x.href)
)"""

BADGE_EX = r"""JSON.stringify(
  (function(){
    var c = document.querySelector('div[data-e2e="user-post-list"]');
    var li = c ? c.querySelector('li') : null;
    var r = li ? li.getBoundingClientRect() : null;
    return r ? {x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2)} : {x:600,y:400};
  })()
)"""


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

    def wheel(self, x, y, dy=1200):
        self.send("Input.dispatchMouseEvent",
                  {"type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": dy})

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
    subprocess.Popen([EDGE, "--remote-debugging-port=9222", "--user-data-dir=" + UD,
                      "--no-first-run", "--no-default-browser-check", "--disable-sync",
                      "about:blank"],
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                     close_fds=True)
    for _ in range(30):
        time.sleep(2)
        try:
            requests.get(CDP + "/json/version", timeout=3)
            return True
        except Exception:
            pass
    return False


def connect(hint="douyin.com"):
    tabs = [t for t in requests.get(CDP + "/json/list", timeout=20).json()
            if (t.get("type") or "") == "page"]
    tab = next((t for t in tabs if hint in (t.get("url") or "")), None)
    if not tab:
        tab = next((t for t in tabs if "about:blank" not in (t.get("url") or "")), None)
    if not tab:
        tab = requests.put(CDP + "/json/new?about:blank", timeout=25).json()
        time.sleep(2)
    c = Cdp(tab["webSocketDebuggerUrl"])
    c.send("Page.enable")
    c.send("Runtime.enable")
    try:
        c.send("Page.bringToFront")
    except Exception:
        pass
    return c


def main():
    url = sys.argv[1]
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    if not ensure_edge():
        return 1
    c = connect()
    t = {}
    for attempt in (1, 2, 3):
        try:
            c.send("Page.navigate", {"url": url})
            for _ in range(20):
                time.sleep(1.5)
                raw = c.eval(TEXTEX)
                if raw:
                    t = json.loads(raw)
                    if (t.get("text") or "").strip():
                        break
            if (t.get("text") or "").strip():
                break
        except Exception as e:
            print("nav attempt %d fail: %s" % (attempt, str(e)[:80]), flush=True)
            try:
                c.close()
            except Exception:
                pass
            time.sleep(8)
            c = connect()

    json.dump(t, open(os.path.join(outdir, "profile.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    txt = t.get("text") or ""
    m = re.search(r"作品\s*(\d+)", txt)
    target = int(m.group(1)) if m else None
    print("PROFILE:", txt[:400], flush=True)
    print("declared works:", target, flush=True)

    # switch to the 作品 tab if needed, then scroll the inner list
    seen = {}
    rounds = 0
    stagnant = 0
    while rounds < 60 and stagnant < 6:
        rounds += 1
        try:
            cards = json.loads(c.eval(CARDS_EX) or "[]")
            pos = json.loads(c.eval(BADGE_EX) or "{}")
        except Exception as e:
            print("  eval fail: %s" % str(e)[:60], flush=True)
            try:
                c.close()
            except Exception:
                pass
            time.sleep(8)
            c = connect()
            continue
        new = 0
        for it in cards:
            h = it.get("href")
            if h and h not in seen:
                seen[h] = it
                new += 1
        print("  round %2d: cards=%d total=%d new=%d" % (rounds, len(cards), len(seen), new), flush=True)
        stagnant = stagnant + 1 if new == 0 else 0
        if target and len(seen) >= target and stagnant >= 2:
            print("  reached declared count", flush=True)
            break
        try:
            c.wheel(pos.get("x", 600), pos.get("y", 400), 1500)
        except Exception:
            pass
        time.sleep(2.2)

    items = list(seen.values())
    out = {"url": t.get("url") or url, "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "declared": target, "count": len(items), "meta": {"body": txt}, "items": items}
    json.dump(out, open(os.path.join(outdir, "videos.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\nvideos=%d (declared=%s) -> %s/videos.json" % (len(items), target, outdir), flush=True)
    for it in items:
        print("  -", it["href"], "|", it["card"][:78])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
