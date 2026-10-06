# -*- coding: utf-8 -*-
"""裴洪川《趋势结构交易法》风险维度实证（回答"有没有量化价值"）

上一轮测的是 20日均值收益 → 对他体系不公平（他讲的是赔率与回撤）。
本轮改测两件事：
  实验A：他的「结构」状态（有序上涨 / 无序 / 跌破前低）能否区分前瞻风险画像
  实验B（核心）：他的「止损=交易失效位」能否改善风险调整后收益
        A组 = 买入后持有20日
        B组 = 买入后若收盘跌破「最近已确认的摆动低点」→ 次日开盘止损，否则持有20日

因果性：分型用 right=2 确认 → 该摆动点在 index+2 才可用（无未来函数）。
数据：hunter.db kline_daily_qfq（前复权日K）
"""
import sqlite3
import sys
import time

import numpy as np

DB = "file:D:/Hermes Agent CN Desktop/hunter-v2/data/hunter.db?mode=ro"
TABLE = "kline_daily_qfq"
FWD = 20
STEP = 5
RIGHT = 2          # 分型确认需要右侧 RIGHT 根K
SWING_MIN_GAP = 3  # 相邻同类摆动点最小间隔，避免噪声


def load():
    con = sqlite3.connect(DB, uri=True, timeout=60)
    t0 = time.time()
    rows = con.execute(
        "select code, date, open, high, low, close from %s" % TABLE).fetchall()
    con.close()
    print("fetched %d rows in %.1fs" % (len(rows), time.time() - t0), flush=True)

    # group by code, preserving row order; assume file already code-major
    codes, idx = [], {}
    for r in rows:
        c = r[0]
        if c not in idx:
            idx[c] = len(codes)
            codes.append([])
        codes[idx[c]].append(r)
    print("codes %d" % len(codes), flush=True)
    return codes


def confirm_swings(high, low, right=RIGHT):
    """返回 confirmed swings: [(confirm_idx, kind, price)]  kind: 1=high, -1=low"""
    n = len(high)
    out = []
    for i in range(right, n - right):
        seg_h = high[i - right:i + right + 1]
        seg_l = low[i - right:i + right + 1]
        if high[i] == seg_h.max() and (seg_h == high[i]).sum() == 1:
            out.append((i + right, 1, float(high[i])))
        if low[i] == seg_l.min() and (seg_l == low[i]).sum() == 1:
            out.append((i + right, -1, float(low[i])))
    out.sort(key=lambda x: x[0])
    return out


def run():
    groups = load()
    rec = {k: [] for k in ("ord_mean", "ord_mdd", "ord_mfe", "ord_out", "ord_stop",
                           "dis_mean", "dis_mdd", "dis_mfe",
                           "brk_mean", "brk_mdd", "brk_mfe",
                           "base_mean", "base_mdd", "base_mfe")}
    year_rec = {}
    n_codes = 0

    for seq in groups:
        n = len(seq)
        if n < 300:
            continue
        try:
            date = [r[1] for r in seq]
            o = np.array([float(r[2]) for r in seq])
            h = np.array([float(r[3]) for r in seq])
            l = np.array([float(r[4]) for r in seq])
            c = np.array([float(r[5]) for r in seq])
        except Exception:
            continue
        if not np.isfinite(c).all() or not np.isfinite(h).all() or \
           not np.isfinite(l).all() or (c <= 0).any() or (l <= 0).any():
            continue
        n_codes += 1

        sw = confirm_swings(h, l)
        if len(sw) < 6:
            continue
        # 逐 bar 维护"截至该 bar 已确认"的摆动序列
        sw_ptr = 0
        hi_list, lo_list = [], []      # (idx, price) 已确认
        for t in range(300, n - FWD - 1, STEP):
            while sw_ptr < len(sw) and sw[sw_ptr][0] <= t:
                _, k, px = sw[sw_ptr]
                (hi_list if k == 1 else lo_list).append(px)
                sw_ptr += 1
            if len(hi_list) < 3 or len(lo_list) < 3:
                continue

            H = hi_list[-3:]
            L = lo_list[-3:]
            up_struct = all(H[i + 1] > H[i] for i in range(len(H) - 1)) and \
                        all(L[i + 1] > L[i] for i in range(len(L) - 1))
            down_struct = all(H[i + 1] < H[i] for i in range(len(H) - 1)) and \
                          all(L[i + 1] < L[i] for i in range(len(L) - 1))
            broke_low = c[t] < L[-1]

            entry = c[t]
            win = slice(t + 1, t + 1 + FWD)
            ret = c[t + FWD] / entry - 1.0
            mdd = l[win].min() / entry - 1.0
            mfe = h[win].max() / entry - 1.0

            # ---- 实验B：失效位止损 ----
            stop_px = L[-1]
            stop_ret = ret
            stop_hit = False
            for k in range(t + 1, t + 1 + FWD):
                if c[k] < stop_px:
                    nx = min(k + 1, t + FWD)
                    stop_ret = o[nx] / entry - 1.0
                    stop_hit = True
                    break

            if up_struct:
                rec["ord_mean"].append(ret); rec["ord_mdd"].append(mdd); rec["ord_mfe"].append(mfe)
                rec["ord_stop"].append(stop_ret)
                rec["ord_out"].append(1.0 if stop_hit else 0.0)
                y = str(date[t])[:4]
                year_rec.setdefault(y, {"a": [], "b": [], "hit": []})
                year_rec[y]["a"].append(ret)
                year_rec[y]["b"].append(stop_ret)
                year_rec[y]["hit"].append(1.0 if stop_hit else 0.0)
            elif down_struct:
                rec["brk_mean"].append(ret); rec["brk_mdd"].append(mdd); rec["brk_mfe"].append(mfe)
            else:
                rec["dis_mean"].append(ret); rec["dis_mdd"].append(mdd); rec["dis_mfe"].append(mfe)
            rec["base_mean"].append(ret); rec["base_mdd"].append(mdd); rec["base_mfe"].append(mfe)

    def line(name, m, d, f):
        if len(m) < 500:
            return dict(组=name, n=len(m), 备注="样本不足")
        m = np.array(m); d = np.array(d); f = np.array(f)
        return dict(组=name, n=len(m),
                    均值收益=round(m.mean() * 100, 2),
                    胜率=round((m > 0).mean() * 100, 1),
                    平均最大不利=round(d.mean() * 100, 2),
                    平均最大有利=round(f.mean() * 100, 2),
                    赔率=round(f.mean() / abs(d.mean()), 2),
                    收益回撤比=round(m.mean() / abs(d.mean()), 3),
                    p5分位=round(np.percentile(m, 5) * 100, 2))

    rowsA = [line("全样本(基准)", rec["base_mean"], rec["base_mdd"], rec["base_mfe"]),
             line("结构有序上涨(HH+HL)", rec["ord_mean"], rec["ord_mdd"], rec["ord_mfe"]),
             line("结构有序下跌(LH+LL)", rec["brk_mean"], rec["brk_mdd"], rec["brk_mfe"]),
             line("结构无序(震荡)", rec["dis_mean"], rec["dis_mdd"], rec["dis_mfe"])]

    a = np.array(rec["ord_mean"]); b = np.array(rec["ord_stop"]); hit = np.array(rec["ord_out"])
    amdd = np.array(rec["ord_mdd"])

    def tail(x, th):
        return round(float((x < th).mean()) * 100, 2)

    def calm(x, dd):
        return round(float(x.mean() / abs(np.array(dd).mean())), 3)

    rowsB = [dict(方案="A 买入后持有20日", n=len(a),
                  均值收益=round(a.mean() * 100, 2), 胜率=round((a > 0).mean() * 100, 1),
                  p5分位=round(np.percentile(a, 5) * 100, 2),
                  p10分位=round(np.percentile(a, 10) * 100, 2),
                  亏超10pct=tail(a, -0.10), 亏超15pct=tail(a, -0.15), 亏超20pct=tail(a, -0.20),
                  收益回撤比=calm(a, amdd)),
             dict(方案="B 跌破失效位止损", n=len(b),
                  均值收益=round(b.mean() * 100, 2), 胜率=round((b > 0).mean() * 100, 1),
                  p5分位=round(np.percentile(b, 5) * 100, 2),
                  p10分位=round(np.percentile(b, 10) * 100, 2),
                  亏超10pct=tail(b, -0.10), 亏超15pct=tail(b, -0.15), 亏超20pct=tail(b, -0.20),
                  收益回撤比=calm(b, amdd))]

    def pr(title, rows_):
        print("\n" + "=" * 118)
        print(title)
        print("=" * 118)
        if not rows_:
            print("(无)"); return
        keys = list(rows_[0].keys())
        w = {k: max(len(str(k)), max(len(str(r.get(k, ""))) for r in rows_)) + 2 for k in keys}
        print("".join(str(k).ljust(w[k]) for k in keys))
        for r in rows_:
            print("".join(str(r.get(k, "")).ljust(w[k]) for k in keys))

    print("\n样本覆盖: codes=%d  有序上涨样本=%d" % (n_codes, len(a)))
    pr("【实验A】他的「结构」状态 → 前瞻20日风险画像（%）", rowsA)
    pr("【实验B·核心】他的「失效位止损」在「有序上涨」入场下的效果（%）", rowsB)
    print("\n止损触发率: %.1f%%" % (hit.mean() * 100))
    print("收益变化: A %.3f%% → B %.3f%%  (Δ %+.3f%%)" %
          (a.mean() * 100, b.mean() * 100, (b.mean() - a.mean()) * 100))
    print("左尾变化: 5分位 %.2f%% → %.2f%%   10分位 %.2f%% → %.2f%%" %
          (np.percentile(a, 5) * 100, np.percentile(b, 5) * 100,
           np.percentile(a, 10) * 100, np.percentile(b, 10) * 100))
    print("最惨单笔: A %.1f%%  B %.1f%%" % (a.min() * 100, b.min() * 100))
    print("尾部概率:  亏>10%%: A %.2f%% → B %.2f%%   亏>15%%: A %.2f%% → B %.2f%%   亏>20%%: A %.2f%% → B %.2f%%" %
          ((a < -0.10).mean() * 100, (b < -0.10).mean() * 100,
           (a < -0.15).mean() * 100, (b < -0.15).mean() * 100,
           (a < -0.20).mean() * 100, (b < -0.20).mean() * 100))

    print("\n分年度（有序上涨样本）")
    print("%-6s %8s %10s %10s %10s %8s" % ("年", "n", "A持有", "B止损", "Δ", "止损率"))
    for y in sorted(year_rec):
        d = year_rec[y]
        if len(d["a"]) < 200:
            continue
        aa, bb = np.array(d["a"]), np.array(d["b"])
        print("%-6s %8d %9.2f%% %9.2f%% %9.2f%% %7.1f%%" %
              (y, len(aa), aa.mean() * 100, bb.mean() * 100,
               (bb.mean() - aa.mean()) * 100, np.mean(d["hit"]) * 100))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
