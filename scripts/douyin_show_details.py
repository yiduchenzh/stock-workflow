# -*- coding: utf-8 -*-
"""Dump 章节要点 from douyin video details."""
import json
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "data/douyin/peihongchuan/video_details.json"
d = json.load(open(path, encoding="utf-8"))


def extract(text):
    t = text or ""
    i = t.find("章节要点")
    if i < 0:
        return ""
    seg = t[i + 4:]
    # cut at the episode marker or 发布时间/评论
    for stop in ["发布时间：", "全部评论", "第1集 |", "点击加载更多"]:
        j = seg.find(stop)
        if j > 0:
            seg = seg[:j]
    return seg.strip()


rows = []
for href, v in d.items():
    t = v.get("text") or ""
    title = (v.get("title") or "").replace(" - 抖音", "")
    m = re.search(r"第\s*(\d+)\s*集", title) or re.search(r"第\s*(\d+)\s*集", t)
    ep = int(m.group(1)) if m else 0
    rows.append((ep, title, extract(t), href))

rows.sort(key=lambda r: (r[0] == 0, r[0]))
print("total=%d with_summary=%d\n" % (len(rows), sum(1 for r in rows if r[2])))
for ep, title, sec, href in rows:
    print("=" * 90)
    print("[第%s集] %s" % (ep or "?", title[:70]))
    print("url:", href)
    print(sec[:1400] if sec else "(无章节要点)")
    print()
