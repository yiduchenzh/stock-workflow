# -*- coding: utf-8 -*-
"""Export all 裴洪川 transcripts + AI 章节要点 into one markdown reference file."""
import json
import re

D = "data/douyin/peihongchuan"
det = json.load(open(D + "/video_details.json", encoding="utf-8"))
eps = json.load(open(D + "/_mix_episodes.json", encoding="utf-8"))
try:
    asr = json.load(open(D + "/transcripts.json", encoding="utf-8"))
except Exception:
    asr = {}


def chapter(text):
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


lines = ["# 裴洪川 · 抖音全量内容（技术演示 + 交易技术）", "",
         "> 采集：2026-10-05 · 视频来源：抖音 @裴洪川（抖音号 21412844837，财咨道信息技术有限公司投资顾问）",
         "> 主页：https://www.douyin.com/user/MS4wLjABAAAAQIy4oJrNtrrrVrE4D2wLY17Sno_lk3BH54tFz6hKZgh12Hcnm_AQjpwIo6-svTRO",
         "> 字幕：本地 faster-whisper large-v3-turbo 转写；「章节要点」为抖音平台 AI 摘要", ""]

for col in ["技术演示", "交易技术"]:
    lines.append("\n# 合集：%s\n" % col)
    for i, e in enumerate(eps.get(col, []), 1):
        href = "https://www.douyin.com/video/" + e["aweme_id"]
        v = det.get(href) or {}
        a = asr.get(e["aweme_id"]) or {}
        lines.append("---\n")
        lines.append("## %s 第%d集｜%s  _(%ss)_\n" % (col, i, e["desc"].split("#")[0].strip(), e["duration_s"]))
        lines.append("视频：%s\n" % href)
        ch = chapter(v.get("text"))
        if ch:
            lines.append("**平台AI章节要点**：%s\n" % ch)
        body = (a.get("asr") or "").strip()
        if body:
            lines.append("**字幕全文**：\n")
            lines.append(body + "\n")
        else:
            lines.append("_(字幕未采集)_\n")

open(D + "/裴洪川-全量字幕与要点.md", "w", encoding="utf-8").write("\n".join(lines))
print("written", D + "/裴洪川-全量字幕与要点.md",
      "entries", sum(len(eps.get(c, [])) for c in ("技术演示", "交易技术")),
      "with_asr", sum(1 for c in ("技术演示", "交易技术") for e in eps.get(c, [])
                      if (asr.get(e["aweme_id"]) or {}).get("asr")))
