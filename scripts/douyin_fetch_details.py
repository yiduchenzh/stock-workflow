# -*- coding: utf-8 -*-
"""Fetch douyin video detail pages (AI 章节要点) for a harvested user.

Usage:
  python scripts/douyin_fetch_details.py <outdir> [--filter "板块,盯盘,共创"]
Reads  <outdir>/videos.json
Writes <outdir>/video_details.json   (incrementally)
"""
import json
import os
import sys
import time

import requests
import websocket

CDP = "http://127.0.0.1:9222"

VEX = r"""JSON.stringify({
  title: document.title,
  url: location.href,
  text: (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').slice(0, 6000),
  src: (function(){var v=document.querySelector('video'); return v ? (v.src||v.currentSrc||'') : '';})(),
  dur: (function(){var v=document.querySelector('video'); return v ? v.duration : 0;})()
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
    outdir = sys.argv[1]
    blacklist = []
    if "--filter" in sys.argv:
        blacklist = [s.strip() for s in sys.argv[sys.argv.index("--filter") + 1].split(",") if s.strip()]

    vj_path = os.path.join(outdir, "videos.json")
    if "--items" in sys.argv:
        vj_path = sys.argv[sys.argv.index("--items") + 1]
    vj = json.load(open(vj_path, encoding="utf-8"))
    items = vj.get("items") or []
    if blacklist:
        kept = [it for it in items
                if not any(b in (it.get("card") or "") for b in blacklist)]
        print("filter %s : %d -> %d" % (blacklist, len(items), len(kept)), flush=True)
        items = kept

    out_path = os.path.join(outdir, "video_details.json")
    out = {}
    if os.path.exists(out_path):
        try:
            out = json.load(open(out_path, encoding="utf-8"))
        except Exception:
            out = {}
    todo = [it for it in items if it.get("href") and (
        it["href"] not in out
        or not any(k in (out[it["href"]].get("text") or "") for k in ("章节要点", "发布时间")))
    ]
    print("target=%d cached=%d todo=%d" % (len(items), len(out), len(todo)), flush=True)

    c = connect()
    ok = 0
    for i, it in enumerate(todo):
        href = it["href"]
        for attempt in (1, 2):
            try:
                c.send("Page.navigate", {"url": href})
                time.sleep(10)
                d = {}
                for _ in range(16):
                    raw = c.eval(VEX)
                    if raw:
                        d = json.loads(raw)
                        txt = d.get("text") or ""
                        if "章节要点" in txt:
                            break
                        if "发布时间" in txt and (d.get("src") or ""):
                            # info block rendered; give the AI summary a bit more time once
                            pass
                    time.sleep(1.5)
                if not (d.get("text") or ""):
                    raise RuntimeError("empty")
                d["list_card"] = it.get("card")
                out[href] = d
                ok += 1
                tmp = out_path + ".tmp"
                json.dump(out, open(tmp, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=1)
                os.replace(tmp, out_path)
                print("[%2d/%2d] OK %s" % (i + 1, len(todo), (d.get("title") or "")[:50]), flush=True)
                break
            except Exception as e:
                print("[%2d/%2d] try%d FAIL %s" % (i + 1, len(todo), attempt, str(e)[:60]), flush=True)
                try:
                    c.close()
                except Exception:
                    pass
                time.sleep(12)
                try:
                    c = connect()
                except Exception as e2:
                    print("   reconnect fail: %s" % str(e2)[:50], flush=True)
        time.sleep(3)
    print("\ndone new=%d total=%d -> %s" % (ok, len(out), out_path), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
