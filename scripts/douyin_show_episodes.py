# -*- coding: utf-8 -*-
"""Dump 章节要点 for all collected douyin videos, ordered by collection+episode."""
import json
import re

OUTDIR = "data/douyin/peihongchuan"
det = json.load(open(OUTDIR + "/video_details.json", encoding="utf-8"))
eps = json.load(open(OUTDIR + "/_mix_episodes.json", encoding="utf-8"))


def extract(text):
    t = text or ""
    i = t.find("章节要点")
    if i < 0:
        return ""
    seg = t[i + 4:]
    for stop in ["发布时间：", "全部评论", "点击加载更多", "内容由AI生成"]:
        j = seg.find(stop)
        if j > 0:
            seg = seg[:j]
    return seg.strip()


rows = []
for col, lst in eps.items():
    for i, e in enumerate(lst, 1):
        href = "https://www.douyin.com/video/" + e["aweme_id"]
        v = det.get(href) or {}
        sec = extract(v.get("text"))
        rows.append((col, i, e["desc"], sec, href, e["duration_s"]))

print("total=%d with_summary=%d\n" % (len(rows), sum(1 for r in rows if r[3])))
for col, i, desc, sec, href, dur in rows:
    print("=" * 92)
    print("【%s 第%d集】%s  (%ss)" % (col, i, desc.split(" ")[0], dur))
    print(sec if sec else "(无AI章节要点 — 待ASR)")
    print()
