import re
from pathlib import Path

ENG = {
    "①昨收战法": Path(r"D:\Hermes Agent CN Desktop\hunter-v2\backend\auto_trader.py"),
    "②昨收15分K": Path(r"D:\Hermes Agent CN Desktop\hunter-v2\backend\prevclose15_auto.py"),
    "③缠论": Path(r"D:\Hermes Agent CN Desktop\hunter-v2\backend\chan_auto_trader.py"),
}
PAT = {
    "数据获取": r"(get_all_quotes|quotes_map|kline\.get_kline|sqlite3|def _daily_rows|kline_cache|KlineCache|stock_sdk|mootdx|gtimg|push2)",
    "选股入口": r"(def _(?:scan_pool|auto_select|select_universe|do_select)|universe|strong_sectors|chanlun_scan|rust_)",
    "盯盘节奏": r"(TICK_SEC|time\.sleep\(|tick_sec|\"09:|'09:|14:5|15:0)",
    "记账口径": r"(SimAccount|_fees|fee_rate|commission|stamp|手续费)",
}
for k, p in ENG.items():
    t = p.read_text(encoding="utf-8", errors="ignore")
    print("### %s (%d 行)" % (k, len(t.splitlines())))
    for label, pat in PAT.items():
        hits = re.findall(pat, t)
        names = sorted(set(x if isinstance(x, str) else x[0] for x in hits))
        print("   %-6s 命中%3d  %s" % (label, len(hits), ", ".join(names[:9])))
    # 显式取数 URL/库
    urls = sorted(set(re.findall(r"https?://([a-z0-9\.\-]+)/", t)))
    print("   URL域名:", ", ".join(urls[:8]) or "-")
    dbs = sorted(set(re.findall(r'([\w\-\.]+\.db)', t)))
    print("   本地库  :", ", ".join(dbs[:8]) or "-")
    print()
