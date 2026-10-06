# -*- coding: utf-8 -*-
"""Classify 裴洪川 videos by douyin collection (合集) name."""
import json
import re
import sys

path = "data/douyin/peihongchuan/video_details.json"
d = json.load(open(path, encoding="utf-8"))

MARK = "下载客户端，桌面快捷访问 下载"


KNOWN = ["技术演示", "交易技术", "股市解读", "交易心法", "技术分享"]


def collection(text):
    i = (text or "").find(MARK)
    if i < 0:
        return "?"
    tail = text[i + len(MARK):]
    head = tail[:60]
    for k in KNOWN:
        if k in head:
            return k
    m = re.search(r"(\d{1,2}:\d{2})", head)
    if m and m.start() == 0:
        return "(无合集)"
    return "(无合集)"


rows = []
for href, v in d.items():
    t = v.get("text") or ""
    col = collection(t)
    title = (v.get("list_card") or "").split(" ", 1)
    card = v.get("list_card") or ""
    m = re.search(r"第\s*(\d+)\s*集", t)
    ep = int(m.group(1)) if m else 0
    has = "章节要点" in t
    rows.append((col, ep, card, has, href))

order = {}
for r in rows:
    order.setdefault(r[0], []).append(r)

for col in sorted(order, key=lambda c: -len(order[c])):
    print("\n" + "#" * 80)
    print("### 合集: %s  (%d 条)" % (col, len(order[col])))
    for c, ep, card, has, href in sorted(order[col], key=lambda x: x[1]):
        print("  第%-3s集 %s %s" % (ep or "?", "[有要点]" if has else "[无要点]", card[:64]))
        print("        ", href)
