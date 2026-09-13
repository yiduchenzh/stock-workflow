# -*- coding: utf-8 -*-
"""战法进化引擎（老陈 2026-08-08 开工落实：L1滚动再优化 + L2 Walk-forward 防过拟合 + L3 失效报警）

设计（金融事业部）：
  L1 滚动再优化 —— 定期重跑参数网格，用最新数据自动更新最优参数
  L2 Walk-forward —— 历史切训练段(前80%)搜参 + 验证段(后20%)检验，
                      只在验证段也通过才采用 → 防过拟合保险丝
  L3 失效报警     —— 监控近期回测收益 vs 基准，连续跑输 → 提示"该进化了"

用法（CLI, 由 main.py 注册）：
  python main.py evolve --codes "001267,002552,300319,600206,002594" --grid-fast
  python main.py evolve --codes "001267,002552,300319,600206,002594"
  python main.py monitor --codes "001267,002552,300319,600206,002594"

产物：
  best_params.json        —— 当前生效参数（evolve 后更新，limitup_backtest 读取）
  evolve_history.json     —— 进化历史（每次进化的参数/训练/验证/采用与否，前端可展示）
"""
from __future__ import annotations

import itertools
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import backtest
from backtest import backtest_full_pro
from datafeed import fetch_daily_kline

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BEST_PARAMS_FILE = os.path.join(BASE_DIR, "best_params.json")
HISTORY_FILE = os.path.join(BASE_DIR, "evolve_history.json")

# 默认强势池（老陈体系：战法只适用强势池）
DEFAULT_CODES = ["001267", "002552", "300319", "600206", "002594"]

# 默认参数网格（沿用已实测的 960 组合空间）
DEFAULT_GRID = {
    "hold_min": [3, 4, 5, 6, 7],
    "t0_gap_pct": [2.0, 3.0, 4.0, 5.0],
    "t0_amp_pct": [1.5, 2.0, 2.5, 3.0],
    "t0_drop_ratio": [0.3, 0.4, 0.5, 0.6],
    "add_vol": [1.0, 1.2, 1.5],
}
FAST_GRID = {
    "hold_min": [3, 5, 7],
    "t0_gap_pct": [3.0, 4.0, 5.0],
    "t0_amp_pct": [1.5, 2.0, 2.5],
    "t0_drop_ratio": [0.3, 0.5],
    "add_vol": [1.0, 1.2],
}
# 重进参数单独小网格（与5参数解耦，避免组合爆炸）
RE_GRID = {"re_entry_hold": [4, 5, 6], "re_entry_cd": [2, 3, 4]}


def _load_json(path: str, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def load_best_params() -> Dict[str, Any]:
    """读取当前生效参数（best_params.json > backtest.BEST_PARAMS）"""
    saved = _load_json(BEST_PARAMS_FILE, {})
    base = dict(getattr(backtest, "BEST_PARAMS", {}))
    base.update(saved)
    return base


def _split_rows(rows: List[Dict[str, Any]], ratio: float = 0.8):
    """切训练段/验证段（按日K行数，训练段在前）"""
    n = len(rows)
    split = max(2, int(n * ratio))
    return rows[:split], rows[split:]


def _filter_min5(min5_by_day, days_set) -> Dict[str, List[Dict[str, Any]]]:
    return {d: ks for d, ks in min5_by_day.items() if d in days_set}


def _run_on(rows_part, min5_part, code, params, min_rows=60) -> Optional[Dict]:
    """在给定数据段上跑回测，返回指标或 None"""
    if len(rows_part) < min_rows:
        return None
    try:
        r = backtest_full_pro(rows_part, min5_part, code, params=params)
        return r.get("完整战法(专业股数)", {})
    except Exception:
        return None


def _grid_search(rows_train_map, min5_train_map, codes, grid, re_params,
                 top_n=5) -> List[Dict]:
    """训练段网格搜索 → 返回按平均收益排序的候选参数"""
    keys = list(grid.keys())
    results = []
    for combo in itertools.product(*[grid[k] for k in keys]):
        params = dict(re_params)
        params.update(dict(zip(keys, combo)))
        totals, mdds = [], []
        for code in codes:
            if code not in rows_train_map:
                continue
            f = _run_on(rows_train_map[code], min5_train_map.get(code, {}), code, params)
            if f:
                totals.append(f.get("总收益%(市值口径)", 0.0))
                mdds.append(f.get("最大回撤%", 0.0))
        if len(totals) >= 1:
            avg_t = sum(totals) / len(totals)
            avg_m = sum(mdds) / len(mdds) if mdds else 0.0
            results.append({"params": params, "train_avg": round(avg_t, 2),
                            "train_mdd": round(avg_m, 2), "n": len(totals)})
    results.sort(key=lambda x: -x["train_avg"])
    return results[:top_n]


def _validate(candidates, rows_val_map, min5_val_map, codes,
              baseline_params) -> Dict:
    """验证段检验：候选 vs 基线，只在验证段也通过才采用"""
    # 基线在验证段的表现
    base_totals = []
    for code in codes:
        if code not in rows_val_map:
            continue
        f = _run_on(rows_val_map[code], min5_val_map.get(code, {}), code, baseline_params)
        if f:
            base_totals.append(f.get("总收益%(市值口径)", 0.0))
    base_avg = sum(base_totals) / len(base_totals) if base_totals else -999.0

    best = None
    for cand in candidates:
        val_totals, val_mdds = [], []
        for code in codes:
            if code not in rows_val_map:
                continue
            f = _run_on(rows_val_map[code], min5_val_map.get(code, {}), code, cand["params"])
            if f:
                val_totals.append(f.get("总收益%(市值口径)", 0.0))
                val_mdds.append(f.get("最大回撤%", 0.0))
        if not val_totals:
            continue
        val_avg = sum(val_totals) / len(val_totals)
        val_mdd = sum(val_mdds) / len(val_mdds) if val_mdds else 0.0
        cand["val_avg"] = round(val_avg, 2)
        cand["val_mdd"] = round(val_mdd, 2)
        # 采用标准：验证段收益 ≥ 基线验证段收益 - 1pp（允许微差）且回撤不爆炸
        if val_avg >= base_avg - 1.0 and val_mdd <= max(base_mdd_of(codes, rows_val_map, min5_val_map, baseline_params) + 5.0, 25.0):
            if best is None or val_avg > best["val_avg"]:
                best = cand
    return {"baseline_val_avg": round(base_avg, 2), "best": best}


def base_mdd_of(codes, rows_val_map, min5_val_map, params) -> float:
    mdds = []
    for code in codes:
        if code not in rows_val_map:
            continue
        f = _run_on(rows_val_map[code], min5_val_map.get(code, {}), code, params)
        if f:
            mdds.append(f.get("最大回撤%", 0.0))
    return sum(mdds) / len(mdds) if mdds else 0.0


def evolve(codes: List[str] = None, grid: Dict = None, train_ratio: float = 0.8,
           re_grid: Dict = None, fast: bool = False) -> Dict:
    """L1+L2 进化主流程"""
    codes = codes or DEFAULT_CODES
    grid = grid or (FAST_GRID if fast else DEFAULT_GRID)
    re_grid = re_grid or RE_GRID
    t0 = time.time()

    print(f"⏳ 进化引擎启动（L1滚动再优化 + L2 Walk-forward 验证）")
    print(f"   股票池: {codes}")
    print(f"   数据: 日K+5分K（mootdx）· 训练段 {int(train_ratio*100)}% / 验证段 {int((1-train_ratio)*100)}%")
    print(f"   网格: {sum(len(v) for v in grid.values())} 参数点 × {len(re_grid.get('re_entry_hold',[]))*len(re_grid.get('re_entry_cd',[]))} 重进组合")

    # 1. 拉数据
    rows_full, min5_full = {}, {}
    for code in codes:
        rows = fetch_daily_kline(code, count=500)
        if len(rows) < 120:
            print(f"  ⚠️ {code} 日K不足({len(rows)}根)，跳过")
            continue
        min5 = _fetch_min5_safe(code)
        rows_full[code] = rows
        min5_full[code] = min5
        print(f"  ✓ {code}: 日K {len(rows)} 根, 分钟 {sum(len(v) for v in min5.values())} 根")
    active = [c for c in codes if c in rows_full]
    if not active:
        return {"error": "无可用股票"}

    # 2. 切训练/验证
    rows_train, rows_val = {}, {}
    min5_train, min5_val = {}, {}
    for code in active:
        tr, va = _split_rows(rows_full[code], train_ratio)
        rows_train[code], rows_val[code] = tr, va
        days_tr = {r["day"] for r in tr}
        days_va = {r["day"] for r in va}
        min5_train[code] = _filter_min5(min5_full[code], days_tr)
        min5_val[code] = _filter_min5(min5_full[code], days_va)

    # 3. 基线 = 当前生效参数
    baseline = load_best_params()

    # 4. 先搜重进参数（小网格，快），再搜5参数
    print(f"\n⏳ 阶段1: 重进参数搜索 ({len(re_grid.get('re_entry_hold',[]))*len(re_grid.get('re_entry_cd',[]))} 组合)...")
    re_candidates = _grid_search(rows_train, min5_train, active, re_grid,
                                 {k: v for k, v in baseline.items() if k not in re_grid}, top_n=3)
    if not re_candidates:
        re_params = {k: v for k, v in baseline.items() if k not in re_grid}
    else:
        re_params = dict(re_candidates[0]["params"])
        print(f"   重进最优: {re_params} (训练段平均 {re_candidates[0]['train_avg']}%)")

    print(f"\n⏳ 阶段2: 5参数网格搜索 ({sum(len(v) for v in grid.values())} 组合 × {len(active)} 只)...")
    candidates = _grid_search(rows_train, min5_train, active, grid, re_params, top_n=8)
    if not candidates:
        return {"error": "训练段网格搜索无结果"}
    print(f"   训练段 TOP3:")
    for i, c in enumerate(candidates[:3], 1):
        print(f"     #{i} {c['params']} → 训练平均 {c['train_avg']}%")

    # 5. 验证段检验（Walk-forward）
    print(f"\n⏳ 阶段3: 验证段检验（防过拟合）...")
    val = _validate(candidates, rows_val, min5_val, active, baseline)
    print(f"   基线验证段平均: {val['baseline_val_avg']}%")
    if val["best"]:
        b = val["best"]
        print(f"   ✅ 候选通过验证: {b['params']}")
        print(f"      训练段 {b['train_avg']}% / 验证段 {b['val_avg']}% (基线 {val['baseline_val_avg']}%)")
        adopted = b["params"]
    else:
        print(f"   ⚠️ 无候选通过验证（全部过拟合）→ 保留当前参数")
        adopted = dict(baseline)

    # 6. 写 best_params.json + 历史
    _save_json(BEST_PARAMS_FILE, adopted)
    hist = _load_json(HISTORY_FILE, [])
    hist.append({
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "codes": active,
        "train_ratio": train_ratio,
        "adopted": adopted,
        "train_avg": round(sum(c["train_avg"] for c in candidates[:3]) / min(3, len(candidates)), 2) if candidates else 0.0,
        "baseline_val_avg": val["baseline_val_avg"],
        "val_avg": val["best"]["val_avg"] if val["best"] else None,
        "adopted_new": bool(val["best"]),
        "elapsed_s": round(time.time() - t0, 1),
    })
    _save_json(HISTORY_FILE, hist[-50:])  # 保留最近50次

    print(f"\n✅ 进化完成（{time.time()-t0:.1f}s）")
    print(f"   采用参数: {adopted}")
    print(f"   已更新: best_params.json + evolve_history.json（共{len(hist)}条历史）")
    if not val["best"]:
        print(f"   ⚠️ 本次未进化（无过拟合通过的候选）——保守正确")
    return {"adopted": adopted, "history_len": len(hist)}


def monitor(codes: List[str] = None, window: int = 20, alert_ratio: float = 0.6) -> Dict:
    """L3 失效报警：最近 window 交易日回测收益 vs 基线，连续跑输报警"""
    codes = codes or DEFAULT_CODES
    baseline = load_best_params()
    print(f"⏳ 失效监控（L3）：最近 {window} 个交易日 · 当前参数 {baseline}")
    totals = []
    for code in codes:
        rows = fetch_daily_kline(code, count=window + 10)
        if len(rows) < max(10, window):
            print(f"  ⚠️ {code} 日K不足，跳过")
            continue
        rows = rows[-window:]
        # ⚠️ 短窗口放宽最小K线数（监控20日窗口只需≥10根）
        f = _run_on(rows, {}, code, baseline, min_rows=10)
        if f:
            totals.append(f.get("总收益%(市值口径)", 0.0))
            print(f"  {code}: 近{window}日收益 {f.get('总收益%(市值口径)',0.0):.2f}% 回撤 {f.get('最大回撤%',0):.1f}%")
    if not totals:
        return {"alert": False, "msg": "无数据"}
    avg = sum(totals) / len(totals)
    # 报警标准：窗口平均收益 < 0 或 低于阈值（简单版：负收益=失效预警）
    alert = avg < 0.0
    print(f"\n近{window}日平均收益: {avg:.2f}%")
    if alert:
        print(f"   🚨 失效报警！近{window}日平均收益为负 → 建议重跑 evolve")
        print(f"   运行: python main.py evolve --codes \"{','.join(codes)}\"")
    else:
        print(f"   ✅ 参数健康（收益为正）")
    return {"alert": alert, "avg": round(avg, 2)}


def _fetch_min5_safe(code: str):
    """拉5分K（复用 limitup_backtest 的 _fetch_min5）"""
    try:
        from limitup_backtest import _fetch_min5
        return _fetch_min5(code)
    except Exception:
        try:
            import sys
            sys.path.insert(0, os.path.join(BASE_DIR, "..", "hunter-v2", "backend"))
            from limitup_backtest import _fetch_min5
            return _fetch_min5(code)
        except Exception as e:
            print(f"  ⚠️ 5分K拉取失败: {e}")
            return {}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="战法进化引擎")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("evolve", help="L1+L2 滚动再优化 + Walk-forward 验证")
    s.add_argument("--codes", type=str, default=",".join(DEFAULT_CODES))
    s.add_argument("--fast", action="store_true", help="快速网格")
    s.add_argument("--train-ratio", type=float, default=0.8)
    m = sub.add_parser("monitor", help="L3 失效报警")
    m.add_argument("--codes", type=str, default=",".join(DEFAULT_CODES))
    m.add_argument("--window", type=int, default=20)
    args = p.parse_args()
    if args.cmd == "evolve":
        evolve([c.strip() for c in args.codes.split(",") if c.strip()],
               fast=args.fast, train_ratio=args.train_ratio)
    elif args.cmd == "monitor":
        monitor([c.strip() for c in args.codes.split(",") if c.strip()], window=args.window)
