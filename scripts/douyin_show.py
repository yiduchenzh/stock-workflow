# -*- coding: utf-8 -*-
"""Print scraped douyin video page texts (strip UI noise)."""
import json
import sys

start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
end = int(sys.argv[2]) if len(sys.argv) > 2 else 999

d = json.load(open("data/douyin/video_details.json", encoding="utf-8"))
print("count =", len(d))
NOISE = ["开启读屏标签", "读屏标签已关闭", "精选", "推荐", "AI抖音", "关注", "朋友", "我的",
         "直播", "放映厅", "短剧", "小游戏", "搜索", "充钻石", "客户端", "壁纸", "通知",
         "消息", "投稿", "登录", "抖音", "首页", "下载", "京ICP", "京公网", "营业执照",
         "违法和不良信息", "算法推荐", "用户服务协议", "隐私政策", "账号找回", "联系我们",
         "加入我们", "友情链接", "站点地图", "广告投放", "举报", "ICP备", "网络文化经营",
         "广播电视节目制作", "增值电信业务", "互联网宗教", "药品医疗器械", "互联网新闻"]


def clean(t):
    t = t or ""
    for n in NOISE:
        t = t.replace(n, " ")
    t = " ".join(t.split())
    return t


for i, (href, v) in enumerate(d.items(), 1):
    if i < start or i > end:
        continue
    print("=" * 78)
    print("[%d] %s" % (i, (v.get("title") or "").replace(" - 抖音", "")))
    print("url:", href)
    print("---")
    print(clean(v.get("text"))[:1000])
    print()
