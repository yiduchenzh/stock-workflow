# -*- coding: utf-8 -*-
"""
main.py — limitup-system CLI 入口

用法（示例）：
  python main.py screen --top 20           全市场打板选股（涨幅+跌幅榜，逐只评分）
  python main.py scan 600519,000063        指定股票池打板选股
  python main.py analysis 600519           单只多周期四级金字塔分析
  python main.py intraday 600519           盘中昨收价战法决策（分钟K）
  python main.py backtest 600519 --count 400   双回测（打板隔日 + 昨收战法）
  python main.py stats 600519 --count 400  打板形态历史统计（涨停日前一日形态分布）

所有命令输出中文表格，可直接对照盘面使用。
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List

import backtest
import datafeed
import multi_timeframe
import screener
import strategy
from datafeed import attach_prev_close, fetch_daily_kline


# ------------------------------------------------------------- 表格输出 ----

def fmt_table(headers: List[str], rows: List[List[Any]], title: str = "") -> str:
    """简单对齐表格（中文按2字符宽估算）。"""
    if title:
        print(f"\n=== {title} ===")
    w = []
    for i, h in enumerate(headers):
        width = len(str(h)) * 2
        for r in rows:
            width = max(width, len(str(r[i])) * 2)
        w.append(width)
    line = "+".join("-" * x for x in w)
    out = [line]
    out.append("+".join(str(h).ljust(w[i] // 2 + (w[i] % 2)) if _is_cjk(str(h)) else str(h).ljust(w[i])
                        for i, h in enumerate(headers)))
    out.append(line)
    for r in rows:
        cells = []
        for i, v in enumerate(r):
            s = str(v)
            if _is_cjk(s):
                cells.append(s.ljust(w[i] // 2 + (w[i] % 2)))
            else:
                cells.append(s.ljust(w[i]))
        out.append("+".join(cells))
    out.append(line)
    return "\n".join(out)


def _is_cjk(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


def _dump(d: Dict[str, Any], indent: int = 0) -> None:
    """递归打印 dict。"""
    pad = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            print(f"{pad}{k}:")
            _dump(v, indent + 1)
        elif isinstance(v, list):
            print(f"{pad}{k}:")
            for item in v:
                print(f"{pad}  - {item}")
        else:
            print(f"{pad}{k}: {v}")


# ------------------------------------------------------------- 命令实现 ----

def cmd_screen(top: int, full: bool, max_pages: int, min_amount: float, workers: int) -> None:
    mode = "全量≈5300只" if full else f"两端({max_pages * 2 * 100}只)"
    print(f"⏳ 拉取全市场列表（新浪，{mode}）...")
    mkt = datafeed.fetch_market_list(max_pages=max_pages, direction="full" if full else "all")
    # 初筛：排除 ST/新股/停牌/低价，成交额下限过滤死票
    pool = [m for m in mkt if m["trade"] > 0
            and not m["name"].startswith(("ST", "*ST", "N", "C"))
            and m["trade"] >= 3.0
            and m["amount"] >= min_amount * 1e8]
    print(f"市场池 {len(mkt)} 只 → 初筛后 {len(pool)} 只（排除ST/新股/停牌/低价/成交额<{min_amount}亿）")
    print(f"⏳ 并发{workers}线程逐只分析日K（进度每200只）...")
    code_to_name = {m["code"]: m["name"] for m in pool}
    results = screener.run_screener(list(code_to_name.keys()), top_n=top, count=120,
                                    workers=workers,
                                    progress=lambda done, total: print(f"  ...{done}/{total}"))
    print(f"\n✅ 命中三类量能形态 {len(results)} 只，TOP{min(top, len(results))}：\n")
    rows = [[r["code"], code_to_name.get(r["code"], ""), r["type"], r["level"], r["score"],
             r["position"], r["price"], r["logic"][:36]] for r in results[:top]]
    print(fmt_table(["代码", "名称", "量能形态", "级", "分", "位置", "现价", "逻辑"],
                    rows, title="打板选股 · 前一日量能三分类"))
    print("\n⚠️ 形态只是概率提升，非100%必涨；次日开盘分时强弱（高开/均价支撑/放量）是最终确认。")


def cmd_scan(codes: List[str], top: int) -> None:
    print(f"⏳ 分析 {len(codes)} 只自选池...")
    results = []
    for code in codes:
        sig = screener.analyze_stock(code, count=120)
        if sig:
            results.append(sig)
    results.sort(key=lambda x: -x["score"])
    rows = [[r["code"], r.get("type", ""), r["level"], r["score"], r["position"],
             r["price"], r["logic"][:40]] for r in results[:top]]
    print(fmt_table(["代码", "量能形态", "级", "分", "位置", "现价", "逻辑"], rows,
                    title="自选池 · 打板潜力评分"))


def cmd_analysis(code: str) -> None:
    print(f"⏳ 多周期四级金字塔分析 {code} ...")
    r = multi_timeframe.multi_timeframe_analysis(code)
    if "error" in r:
        print(r["error"])
        return
    print(f"\n=== {code} 多周期战法（日线→60分→15分→分时）===")
    print(f"方向: {r['direction']} | 建议仓位: {r['position']} | 昨收: {r['prev_close']} | 现价: {r['last_price']}")
    print("综合信号:")
    for s in r["signals"]:
        print(f"  • {s}")
    print(f"\n--- 日线层 ---")
    d = r["daily"]
    print(f"四态: {d['state']} | 均线: MA5={d['ma5']} MA10={d['ma10']} MA20={d['ma20']} "
          f"多头排列={'是' if d['bull_align'] else '否'}")
    lim = d["limitup_signal"]
    if lim["type"] != "无形态":
        print(f"打板形态: {lim['name']}（{lim['score']}分 {lim['level']}级，{lim['position']}）")
        print(f"  逻辑: {lim['logic']}")
    print(f"\n--- 60分层 ---")
    print(f"{r['min60']['level']} | {r['min60']['detail']}")
    print(f"\n--- 15分层 ---")
    print(f"{r['min15']['setup']} | {r['min15']['detail']}")
    print(f"\n--- 5分/分时层 ---")
    print(f"开盘3分钟: {r['min5_execute']['signal']} | {r['min5_execute']['detail']}")


def cmd_intraday(code: str) -> None:
    daily = fetch_daily_kline(code, count=20)
    if len(daily) < 2:
        print("日K数据不足")
        return
    daily = attach_prev_close(daily)
    prev_close = daily[-1]["prev_close"]
    # 当日分钟K（新浪5分钟，可能含今天）
    minute5 = datafeed.fetch_minute_kline(code, scale=5, count=96)
    if not minute5:
        print("分钟K数据不足（非交易时段可能为空）")
        return
    today = daily[-1]["day"]
    today_rows = [r for r in minute5 if r["day"].startswith(today)]
    if not today_rows:
        today_rows = minute5[-20:]  # 兜底：最近20根
        print(f"⚠️ 未取到 {today} 当日分钟K，使用最近 {len(today_rows)} 根")
    print(f"\n=== {code} 盘中昨收价战法 ===")
    print(f"昨收基准: {prev_close} | 最新: {today_rows[-1]['close']}")
    r = strategy.full_analysis(today_rows, prev_close)
    st = r["state"]
    print(f"\n日内四态: [{st['state']}]")
    print(f"  {st['detail']}")
    print(f"\n开盘3分钟: [{r['opening_3min']['signal']}]")
    print(f"  {r['opening_3min']['detail']}")
    print(f"\n进场信号: [{r['buy_signal']['signal']}]")
    if r["buy_signal"].get("stop"):
        print(f"  止损参考: {r['buy_signal']['stop']}")
    print(f"  {r['buy_signal']['detail']}")
    print(f"\n离场信号: [{r['sell_signal']['signal']}]")
    print(f"  {r['sell_signal']['detail']}")
    print(f"\nT+0 回转: [{r['t0_signal']['signal']}]")
    if r['t0_signal'].get('ref_price'):
        print(f"  接回/参考价: {r['t0_signal']['ref_price']}")
    print(f"  {r['t0_signal']['detail']}")
    print(f"\n加减仓: [{r['add_reduce']['action']} {r['add_reduce'].get('level', '')}]")
    print(f"  {r['add_reduce']['detail']}")
    print(f"\n仓位方案: [{r['position_plan']['pos']}]")
    print(f"  {r['position_plan']['action']}")


def cmd_backtest(code: str, count: int, min_score: int) -> None:
    print(f"⏳ 回测 {code}（{count}根日K）...")
    result = backtest.run_backtest(code, count=count, min_score=min_score)
    if "error" in result:
        print(result["error"])
        return
    lu = result["打板隔日回测"]
    print(f"\n=== 打板隔日回测（文字①验证）===")
    print(f"策略: {lu['策略']}")
    print(f"笔数: {lu['笔数']} | 胜率: {lu['胜率%']}% | 盈亏比: {lu['盈亏比']} | "
          f"总收益(复合): {lu['总收益%(复合)']}% | 平均每笔: {lu['平均每笔%']}% | 最大回撤: {lu['最大回撤%']}%")
    print("\n按形态分组:")
    rows = [[k, v["笔数"], v["胜率%"], round(v["净收益"], 2)] for k, v in lu["按形态"].items()]
    print(fmt_table(["形态", "笔数", "胜率%", "累计净收益%"], rows))
    if lu["交易明细"]:
        print(f"\n最近{len(lu['交易明细'])}笔明细:")
        rows = [[t["形态日"], t["形态"], t["评分"], t["买入日"], t["买入价"], t["卖出价"],
                 t["净收益%"]] for t in lu["交易明细"][-8:]]
        print(fmt_table(["形态日", "形态", "分", "买入日", "买价", "卖价", "净收益%"], rows))
    pc = result["昨收战法回测"]
    print(f"\n=== 昨收战法回测（文字②验证）===")
    print(f"四态分布: {pc['四态分布']}")
    rows = [[k, v["出现天数"], v["日内胜率%(a)"], v["隔夜胜率%(b)"], v["日内平均净收益%"]]
            for k, v in pc["形态统计"].items()]
    print(fmt_table(["形态", "出现天数", "日内胜率%(纯日内)", "隔夜胜率%(T+1合规)", "日内平均净收益%"], rows))
    print(f"\n口径a(开盘买收盘卖·纯日内参考): {pc['口径a_日内']}")
    print(f"口径b(开盘买次日卖·T+1合规): {pc['口径b_隔夜T+1合规']}")
    print(f"\n⚠️ 回测口径说明: {pc['说明']}")


def cmd_portfolio(codes: List[str], count: int, top_n: int = 0) -> None:
    tn = f"，聚焦TOP{top_n}" if top_n else ""
    print(f"⏳ 完整战法组合回测 {len(codes)} 只（{count}根日K≈{count / 250:.1f}年，等权{tn}）...")
    r = backtest.backtest_full_portfolio(codes, count=count, top_n=top_n or None)
    if "error" in r:
        print(r["error"])
        return
    c = r["组合(等权)"]
    print(f"\n=== 组合回测（等权 {c['股票数']} 只）===")
    print(f"总收益(复合): {c['总收益%(复合)']}% | 年化(近似): {c['年化%(近似)']}% | "
          f"日胜率: {c['日胜率%']}% | 最大回撤: {c['最大回撤%']}%")
    print("\n个股贡献:")
    rows = [[x["代码"], x["总收益%"], x["做T次数"], x["做T收益%"], x["加仓"], x["减仓"], x["持仓周期"]]
            for x in r["个股贡献"]]
    print(fmt_table(["代码", "总收益%", "做T次数", "做T收益%", "加仓", "减仓", "持仓周期"], rows))
    print(f"\n⚠️ {r['诚实声明']}")


def cmd_backtest_full(code: str, count: int) -> None:
    rows = datafeed.fetch_daily_kline(code, count=count)
    if len(rows) < 60:
        print("K线数据不足")
        return
    print(f"⏳ 完整战法回测 {code}（{len(rows)}根日K≈{len(rows) / 250:.1f}年）...")
    r = backtest.backtest_full_tactics(rows, code)
    f = r["完整战法(底仓+做T+加减仓)"]
    print(f"\n=== {code} 完整战法（底仓+T+0+加减仓）vs 纯四态 ===")
    print(f"总收益(复合): {f['总收益%(复合)']}% | 年化(近似): {f['年化%(近似)']}% | "
          f"日胜率: {f['日胜率%']}% | 最大回撤: {f['最大回撤%']}%")
    print(f"做T: {f['做T次数']}次 累计{f['做T累计收益%']}% | 加仓{f['加仓次数']}次 | 减仓{f['减仓次数']}次 | "
          f"持仓周期{f['持仓周期数']}个")
    b = r["对照_纯四态口径b"]
    print(f"\n对照·纯四态口径b(开盘买次日卖): 总收益 {b['总收益%(复合)']}% | 胜率 {b['胜率%']}% | {b['笔数']}笔")
    print(f"\n⚠️ {r['诚实声明']}")


def cmd_stats(code: str, count: int) -> None:
    rows = fetch_daily_kline(code, count=count)
    if len(rows) < 60:
        print("K线数据不足")
        return
    print(f"⏳ 统计 {code} 涨停日前一日量能形态（{len(rows)}根日K）...")
    st = screener.limitup_statistics(rows, code)
    print(f"\n=== {code} 涨停统计 ===")
    print(f"区间内涨停总数: {st['涨停总数']}")
    print("\n涨停日前一日形态分布（口径A：验证'涨停前一日只会归为三类'）:")
    rows_t = [[k, v, st["三类形态占比"][k]] for k, v in st["涨停日前一日形态分布"].items()]
    print(fmt_table(["形态", "涨停日数", "占比%"], rows_t))
    print("\n形态→次日表现（口径B：诚实的真实概率，含全部形态出现日）:")
    rows_t = [[k, v["出现次数"], v["次日涨停率"], v["次日上涨率"], v["次日平均涨幅"], v["连板次数"]]
              for k, v in st["形态→次日涨停率"].items()]
    print(fmt_table(["形态", "出现次数", "次日涨停率%", "次日上涨率%", "次日平均涨幅%", "连板次数"], rows_t))
    print("\n⚠️ 口径A证明'涨停的伏笔在三类形态中'；口径B提醒：形态出现≠次日必涨停，"
          "真实涨停率通常远低于直觉——这就是仓位风控存在的意义。")


# ------------------------------------------------------------- 战法进化 ----


def cmd_evolve(codes: List[str], fast: bool, train_ratio: float) -> None:
    """L1+L2: 滚动再优化 + Walk-forward 防过拟合"""
    import evolve
    evolve.evolve(codes=codes, fast=fast, train_ratio=train_ratio)


def cmd_monitor(codes: List[str], window: int) -> None:
    """L3: 失效报警"""
    import evolve
    evolve.monitor(codes=codes, window=window)


# ------------------------------------------------------------- 入口 ----

def main() -> None:
    p = argparse.ArgumentParser(description="limitup-system — 昨收价+量能三分类交易系统")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("screen", help="全市场打板选股（默认全量≈5300只）")
    s.add_argument("--top", type=int, default=20)
    s.add_argument("--fast", action="store_true", help="快速模式：只扫涨幅+跌幅榜两端")
    s.add_argument("--pages", type=int, default=8, help="fast 模式下每端页数")
    s.add_argument("--min-amount", type=float, default=2.0, help="成交额下限(亿)，过滤死票")
    s.add_argument("--workers", type=int, default=12, help="并发线程数")

    s = sub.add_parser("scan", help="指定股票池打板选股")
    s.add_argument("codes", type=str, help="逗号分隔，如 600519,000063")
    s.add_argument("--top", type=int, default=20)

    s = sub.add_parser("analysis", help="单只多周期四级金字塔")
    s.add_argument("code", type=str)

    s = sub.add_parser("intraday", help="盘中昨收价战法决策")
    s.add_argument("code", type=str)

    s = sub.add_parser("backtest", help="回测（打板隔日 + 昨收战法）")
    s.add_argument("code", type=str)
    s.add_argument("--count", type=int, default=400)
    s.add_argument("--min-score", type=int, default=50)

    s = sub.add_parser("full", help="完整战法回测（底仓+T+0+加减仓 vs 纯四态）")
    s.add_argument("code", type=str)
    s.add_argument("--count", type=int, default=500)

    s = sub.add_parser("portfolio", help="完整战法组合回测（等权多股，可聚焦TOP N）")
    s.add_argument("codes", type=str, help="逗号分隔（PowerShell下加引号防前导零丢失）")
    s.add_argument("--count", type=int, default=500)
    s.add_argument("--top-n", type=int, default=0, help="只取单只收益前N只做组合（实盘聚焦5-8只）")

    s = sub.add_parser("stats", help="涨停日前一日形态统计")
    s.add_argument("code", type=str)
    s.add_argument("--count", type=int, default=400)

    s = sub.add_parser("evolve", help="战法进化引擎 L1+L2（滚动再优化 + Walk-forward 验证）")
    s.add_argument("--codes", type=str, default="001267,002552,300319,600206,002594")
    s.add_argument("--fast", action="store_true", help="快速网格（减少参数点）")
    s.add_argument("--train-ratio", type=float, default=0.8, help="训练段比例（默认0.8）")

    s = sub.add_parser("monitor", help="战法失效报警 L3（近N日收益 vs 基准）")
    s.add_argument("--codes", type=str, default="001267,002552,300319,600206,002594")
    s.add_argument("--window", type=int, default=20, help="监控窗口交易日数")

    args = p.parse_args()
    if args.cmd == "screen":
        cmd_screen(args.top, not args.fast, args.pages, args.min_amount, args.workers)
    elif args.cmd == "scan":
        cmd_scan([c.strip() for c in args.codes.split(",") if c.strip()], args.top)
    elif args.cmd == "analysis":
        cmd_analysis(args.code)
    elif args.cmd == "intraday":
        cmd_intraday(args.code)
    elif args.cmd == "backtest":
        cmd_backtest(args.code, args.count, args.min_score)
    elif args.cmd == "full":
        cmd_backtest_full(args.code, args.count)
    elif args.cmd == "portfolio":
        cmd_portfolio([c.strip() for c in args.codes.split(",") if c.strip()], args.count, args.top_n)
    elif args.cmd == "stats":
        cmd_stats(args.code, args.count)
    elif args.cmd == "evolve":
        cmd_evolve([c.strip() for c in args.codes.split(",") if c.strip()], args.fast, args.train_ratio)
    elif args.cmd == "monitor":
        cmd_monitor([c.strip() for c in args.codes.split(",") if c.strip()], args.window)


if __name__ == "__main__":
    main()
