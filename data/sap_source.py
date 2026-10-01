# -*- coding: utf-8 -*-
"""stock-analysis-plugin 数据源适配层 (stock-workflow 侧)

定位（2026-10-01 实测结论）
--------------------------
**不作主源** —— 实测单只 K 线 ~3.9s（全市场 5000 只 ≈ 324 分钟），且 A 股链路在本机
实际供数方是 **腾讯**（粘性缓存实证），与本工程现有 TDX→腾讯 链同源，不构成独立第二源。

**作两件事**：
  1. **能力补位**（主要价值）: 涨停池(连板/封板资金/炸板)、龙虎榜(净买额+游资解读)、
     两融明细、人气榜、财务比率、交易日历 —— 本工程此前没有或只有单源实现。
  2. **最后一道降级**: 当 market.db / TDX / 腾讯全部失败时兜底（7 源自动切换）。

契约
----
- 桥接实现唯一一份: `stock-analysis-plugin/bridge/sap_bridge.py`
  （经环境变量 SAP_HOME 定位，默认 D:\\Hermes Agent CN Desktop\\stock-analysis-plugin）
- **不安装** 插件到本工程 venv —— 它的 pandas3/akshare 会污染实盘环境；一律 subprocess 调它的 venv。
- volume 单位 = **手**（与本工程 data/sources.py 一致，无需换算）。
- 全部函数失败时返回空 DataFrame / None，**不抛异常**，调用方降级即可。
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys

import pandas as pd

logger = logging.getLogger(__name__)

SAP_HOME = os.environ.get("SAP_HOME") or r"D:\Hermes Agent CN Desktop\stock-analysis-plugin"
_BRIDGE_PATH = os.path.join(SAP_HOME, "bridge", "sap_bridge.py")
_bridge = None
_load_failed = False

# 进程内缓存 probe 结果，避免每只股票都探测一次
_PROBED = None


def _get_bridge():
    """按路径加载共享桥接模块（唯一实现，不复制到本工程）"""
    global _bridge, _load_failed
    if _bridge is not None or _load_failed:
        return _bridge
    try:
        if not os.path.exists(_BRIDGE_PATH):
            logger.info("[SAP] 桥接层不存在: %s（跳过 SAP 数据源）", _BRIDGE_PATH)
            _load_failed = True
            return None
        spec = importlib.util.spec_from_file_location("sap_bridge", _BRIDGE_PATH)
        mod = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("sap_bridge", mod)
        spec.loader.exec_module(mod)
        _bridge = mod
    except Exception as e:
        logger.warning("[SAP] 桥接层加载失败: %s", e)
        _load_failed = True
    return _bridge


def available(force: bool = False) -> bool:
    """SAP 是否可用（探活一次后缓存；失败不重试，避免拖慢主链）"""
    global _PROBED
    if _PROBED is not None and not force:
        return _PROBED
    b = _get_bridge()
    if b is None:
        _PROBED = False
        return False
    try:
        r = b.kline("600519", 2, unit="lots")
        _PROBED = bool(r.get("ok"))
    except Exception:
        _PROBED = False
    if not _PROBED:
        logger.info("[SAP] 不可用（探活失败）")
    return _PROBED


def _df(rows) -> pd.DataFrame:
    """统一列序: date, open, close, high, low, volume（与 data/sources.py 腾讯源一致）"""
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([{"date": r["date"], "open": r["open"], "close": r["close"],
                        "high": r["high"], "low": r["low"], "volume": r["volume"]} for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df


def get_kline_df(code: str, days: int = 250) -> pd.DataFrame:
    """日K（**降级用**）。volume 单位=手"""
    b = _get_bridge()
    if b is None:
        return pd.DataFrame()
    try:
        r = b.kline(code, int(days), unit="lots")
        return _df(r.get("data")) if r.get("ok") else pd.DataFrame()
    except Exception as e:
        logger.debug("[SAP] kline %s 失败: %s", code, e)
        return pd.DataFrame()


# ───────────────── 能力补位（本工程此前没有的数据） ─────────────────
def get_limit_up_pool(date: str | None = None) -> dict | None:
    """涨停池 / 涨停板复盘: {count, max_consecutive_boards, pool[{code,name,consecutive_boards,
    seal_amount,first_seal_time,break_count,turnover_rate,industry,...}]}"""
    b = _get_bridge()
    if b is None:
        return None
    r = b.limit_up_pool(date)
    return r.get("data") if r.get("ok") else None


def get_dragon_tiger(date: str | None = None) -> dict | None:
    """龙虎榜: {count, items[{code,name,net_buy,buy_amount,sell_amount,reason,interpretation}]}"""
    b = _get_bridge()
    if b is None:
        return None
    r = b.dragon_tiger(date)
    return r.get("data") if r.get("ok") else None


def get_margin(code: str) -> list | None:
    """个股融资融券明细（⚠ 交易所口径，通常滞后 1~2 个交易日）"""
    b = _get_bridge()
    if b is None:
        return None
    r = b.margin(code)
    return r.get("data") if r.get("ok") else None


def get_hot_stocks() -> dict | None:
    """全市场人气热搜榜"""
    b = _get_bridge()
    if b is None:
        return None
    r = b.hot_stocks()
    return r.get("data") if r.get("ok") else None


def get_financial_ratios(code: str) -> dict | None:
    """财务比率（⚠ 实测 report_date 字段错误，只用 roe/gross_margin/net_profit_margin/debt_ratio）"""
    b = _get_bridge()
    if b is None:
        return None
    r = b.financials(code)
    return r.get("data") if r.get("ok") else None


def is_trading_day(date: str, market: str = "CN") -> bool | None:
    """交易日历（实测 09-30 交易 / 10-01 休 / 10-08 交易 / 09-25 休，与本工程日历一致）"""
    b = _get_bridge()
    if b is None:
        return None
    r = b.is_trading_day(date, market)
    return r.get("data") if r.get("ok") else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("available:", available())
    df = get_kline_df("600519", 3)
    print("kline\n", df)
    print("is_trading_day 2026-10-01:", is_trading_day("2026-10-01"))
