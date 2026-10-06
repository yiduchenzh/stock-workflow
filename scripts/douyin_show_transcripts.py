# -*- coding: utf-8 -*-
"""Print collected ASR transcripts ordered by collection/episode."""
import json
import sys

D = "data/douyin/peihongchuan"
d = json.load(open(D + "/transcripts.json", encoding="utf-8"))
eps = json.load(open(D + "/_mix_episodes.json", encoding="utf-8"))

start_from = int(sys.argv[1]) if len(sys.argv) > 1 else 0
only_col = sys.argv[2] if len(sys.argv) > 2 else None

for col in ["技术演示", "交易技术"]:
    if only_col and col != only_col:
        continue
    for i, e in enumerate(eps.get(col, []), 1):
        if i < start_from:
            continue
        a = d.get(e["aweme_id"])
        if not a:
            continue
        print("=" * 88)
        print("【%s 第%d集】%s" % (col, i, e["desc"].split("#")[0].strip()))
        print(a.get("asr") or "")
        print()
