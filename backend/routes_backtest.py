"""数据关联层 Web 暴露 — 真实回测/时点对齐/板块钻取.

把先前已落地的数据关联层能力暴露给前端:
① 结果级缓存真实回测 (直接调用 prev_close_strategy 已带缓存的 backtest_single/multitf,
   复用其 _PREV_CACHE / ResultCache, 不重造缓存)。
② as_of 时点对齐 (无未来函数, 把\"某时点能看到的那行\"暴露给前端)。
③ 板块多对多钻取 (get_sector_members 反向查询某板块下所有股票)。
"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Query

router = APIRouter()

logger = logging.getLogger("aurora.routes.backtest")


# ─────────────────────────── ① 真实回测 (结果级缓存) ───────────────────────────
def _fetch_and_backtest(code: str, years: int, capital: float, stop: float, mode: str):
    """拉K线后调用 prev_close_strategy 已带缓存的回测函数.

    返回 {perf, result_summary} 或抛异常(交上层转 error dict)。网络受限拉不到
    K线时抛 RuntimeError, 由 API 层返回 {error, detail}, 绝不 fallback 模拟值。
    """
    import prev_close_strategy as p

    days = max(years * 250, 120)
    df_day = p.fetch_kline(code, max(days, 100))
    if df_day is None or df_day.empty or len(df_day) < 100:
        raise RuntimeError(f"{code}: K线获取失败或不足({0 if df_day is None else len(df_day)}行)")

    # ⭐ P0-① 回测侧强势池预筛（与实盘 runner.py:166-174 同源门槛）: 标注该标的
    #   是否符合强势池。实盘仅对 strong_grade∈{A,B} 或 strong_score≥70 跑昨收战法,
    #   回测同步口径→前端可用 strong_pool 过滤"回测/实盘不同源"的虚高胜率。
    _gate = p._strong_pool_gate(df_day)
    _strong_pool = _gate[0]
    _strong_info = _gate[1]

    if mode == "multitf":
        # 三周期共振: 日线(位置) + m1(开盘3分钟) + m15(盘中执行), 均用原始K线
        df_m1 = p.fetch_kline(code, 2000, tf="m1")
        df_m15 = p.fetch_kline(code, 2000, tf="m15")
        if df_m1.empty or df_m15.empty:
            raise RuntimeError(f"{code}: 分钟K线(m1/m15)获取失败,无法跑 multitf")
        df_m1.attrs["code"] = code
        df_m15.attrs["code"] = code
        df_day.attrs["code"] = code
        result = p.backtest_multitf(df_m1, df_m15, df_day,
                                    capital=capital, stop_pct=min(stop, 0.05))
        return result, mode, _strong_pool, _strong_info

    # 默认 single: 先 generate_signals 生成 prev_close/signal 列
    df_day.attrs["code"] = code
    sig_df = p.generate_signals(df_day)
    result = p.backtest_single(sig_df, capital=capital,
                               entry_mode="next_open", stop_pct=stop)
    return result, mode, _strong_pool, _strong_info


def _fmt_result(code: str, result: dict, mode: str,
                strong_pool: bool = True, strong_info: dict = None) -> dict:
    """把回测返回 dict 收敛为 JSON 友好 + 绩效指标."""
    import prev_close_strategy as p

    perf = p.performance(result)
    meta = {
        "code": code,
        "mode": mode,
        "capital": result.get("capital"),
        "final_equity": result.get("final_equity"),
        "trades_count": len(result.get("trades", [])),
        # ⭐ P0-① 强势池标注: 回测/实盘同源判定结果（前端可据此过滤非强池虚高胜率）
        "strong_pool": bool(strong_pool),
        "strong_grade": (strong_info or {}).get("grade", "?"),
        "strong_score": (strong_info or {}).get("score", 0),
    }
    # 移除 signal_dist/exit_dist 的非JSON计数也可直接传(已是python dict)
    meta["perf"] = perf
    meta["latest_trades"] = result.get("trades", [])[-3:]
    return meta


@router.get("/api/backtest/run")
async def backtest_run(
    codes: str = Query("600519,000858", description="逗号分隔的股票代码"),
    years: int = Query(2, ge=1, le=10),
    capital: float = Query(100000, gt=0),
    mode: str = Query("single", description="single=单标的日线 / multitf=多周期共振"),
    stop: float = Query(0.08, gt=0, lt=1),
):
    """真实回测 API — 复用 prev_close_strategy 已带的结果级缓存.

    注意缓存统计口径: _PREV_CACHE 是模块级共享的磁盘缓存, 每次调用都会累计
    hits/misses。这里取 API 调用前后差值作为\"本次请求\"的命中统计, 避免把历史
    累计当成本次。禁止任何 fallback 模拟值; 拉不到K线返回 {error, detail}。
    """
    code_list = [c.strip() for c in codes.split(",") if c.strip()]

    import prev_close_strategy as p

    s0 = p._PREV_CACHE.stats()
    results = []
    errors = {}
    for code in code_list:
        try:
            result, used_mode, _sp, _sgi = _fetch_and_backtest(code, years, capital, stop, mode)
            results.append(_fmt_result(code, result, used_mode, _sp, _sgi))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[backtest_run] {code} 失败: {e}")
            errors[code] = str(e)
    s1 = p._PREV_CACHE.stats()

    # 本次请求的缓存增量 h/m (Δ 保证与具体历史状态无关; 若关闭缓存则为0)
    delta_hits = max(0, s1["hits"] - s0["hits"])
    delta_misses = max(0, s1["misses"] - s0["misses"])
    total_calls = delta_hits + delta_misses
    delta_rate = round(delta_hits / total_calls * 100, 2) if total_calls else 0.0

    payload = {
        "codes": code_list,
        "period_years": years,
        "capital": capital,
        "mode": mode,
        "results": results,
        # 每标的结果含绩效 + 缓存增量; 顶层再给一次整体缓存统计
        "cache": {
            "hits": delta_hits,
            "misses": delta_misses,
            "hit_rate": delta_rate,
            "size": p._PREV_CACHE.size(),
            "file": str(p._PREV_CACHE.path),
        },
        "errors": errors,
        "disclaimer": "回测结果仅供研究参考,不构成投资建议;数据拉取失败标的已如实标记,无模拟值;"
                      "每标的结果含 strong_pool 强势池判定(与实盘 runner.py 护栏同源: "
                      "strong_grade∈{A,B}或strong_score≥70),非强池标的回测胜率请谨慎解读(实盘只做强势池)",
    }
    # 所有标的都拉不到数据时, 返回显式 {error, detail} 语义, 而非把空结果当成功
    if errors and not results:
        payload["error"] = "K线数据获取失败(网络受限或无此标的)"
        payload["detail"] = errors
    return payload


# ─────────────────────────── ② 至简交易法 (独立新增, 不动 run) ───────────────────────────
@router.get("/api/backtest/zhijian")
async def backtest_zhijian_api(
    code: str = Query("300319", description="股票代码"),
    capital: float = Query(100000, gt=0),
    tf: str = Query("m15", description="分钟周期: m5/m15/m30/m60"),
    min_bars: int = Query(2000, gt=100, le=4000),
):
    """'至简交易法'回测 API — 老陈实盘战法(独立引擎 data/zhijian_backtest)。

    与 /api/backtest/run 完全独立: 调用 data/zhijian_backtest.run_zhijian
    (自带结果级缓存 zhijian_result_cache.json)。本次请求的缓存命中统计取 Δ。
    拉数据失败返回 {error, detail}, 绝不 fallback 模拟值。
    """
    from data.zhijian_backtest import _ZJ_CACHE, run_zhijian

    s0 = _ZJ_CACHE.stats()
    try:
        result = run_zhijian(code, tf=tf, capital=capital, min_bars=min_bars)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[zhijian] {code} 失败: {e}")
        return {"error": f"{code} 至简交易法回测失败(网络受限或无此标的)", "detail": str(e)}

    s1 = _ZJ_CACHE.stats()
    delta_hits = max(0, s1["hits"] - s0["hits"])
    delta_misses = max(0, s1["misses"] - s0["misses"])
    total = delta_hits + delta_misses
    delta_rate = round(delta_hits / total * 100, 2) if total else 0.0

    payload = {
        "code": code,
        "tf": tf,
        "capital": capital,
        "result": result,
        "cache": {
            "hits": delta_hits,
            "misses": delta_misses,
            "hit_rate": delta_rate,
            "size": _ZJ_CACHE.size(),
            "file": str(_ZJ_CACHE.path),
        },
        "disclaimer": "回测结果仅供研究参考,不构成投资建议;数据拉取失败已如实标记,无模拟值",
    }
    return payload


# ─────────────────────────── ③ as_of 时点对齐 ───────────────────────────
@router.get("/api/asof")
async def asof_row_api(
    code: str = Query(..., description="股票代码"),
    date: str = Query(..., description="对齐时点 YYYY-MM-DD"),
    mode: str = Query("latest", description="latest=<=当天最近一期 / prev=<当天 / exact=恰好当天"),
):
    """时点对齐: 拉该股日K后, 用 as_of_row 返回 date 时点\"能看到\"的那一行.

    无未来函数语义: latest 含当天(收盘可知), prev 严格排除当天(需次日确认),
    exact 必须恰好那天。附上 fundamentals 落库基本面(pe/pb) 或注明时点未知。
    """
    try:
        target = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "date 需为 YYYY-MM-DD", "given": date}

    # 拉取日K(足够覆盖 date; 若 date 距今较远则多取)
    days_needed = max(int((datetime.now().date() - target).days * 1.4) + 260, 300)
    from prev_close_strategy import fetch_kline

    try:
        df = fetch_kline(code, days=min(days_needed, 2000))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[asof] {code} K线获取失败: {e}")
        return {"error": f"{code} K线获取失败(网络受限)", "detail": str(e)}
    if df is None or df.empty:
        return {"error": f"{code} 无K线数据(网络受限)"}

    if mode not in ("latest", "prev", "exact"):
        return {"error": "mode 必须为 latest/prev/exact", "given": mode}

    from data.as_of import as_of_row

    row = as_of_row(df, target, mode)
    if row is None:
        return {
            "code": code, "date": date, "mode": mode,
            "found": False,
            "detail": f"在 {date} 时点无【{mode}】可见数据(trade_date 当天无K线或无更早一期)",
        }

    # 附上落库基本面(注明为最近一次刷新的近似, 非该时点精确值)
    fund = {}
    try:
        from data.fundamentals_store import get_fundamentals
        fund = get_fundamentals(code) or {}
    except Exception:  # noqa: BLE001
        fund = {}

    return {
        "code": code,
        "date": date,
        "mode": mode,
        "found": True,
        "row": {
            "trade_date": str(row.get("date"))[:10],
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "volume": row.get("volume"),
        },
        # 当前落库基本面 (最近一次刷新, 非历史时点精确值)
        "fundamentals": {
            "pe_ttm": fund.get("pe_ttm"),
            "pb": fund.get("pb"),
            "as_of_fund_updated": bool(fund),
            "note": "落库基本面为最近刷新值, 非历史时点精确值" if fund else "该股无落库基本面",
        },
        "disclaimer": "as_of 返回某时点可见数据,无未来函数;fundamentals 为最近快照而非历史精确值",
    }
