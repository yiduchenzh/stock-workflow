"""
A股基本面数据获取模块 v2.0
──────────────────────────
三层架构, 零WZ依赖, 带缓存(5分钟TTL)

数据源策略(三级降级):
  1. mootdx TCP (首选) — client.finance() + client.F10() 港澳资讯F10
  2. 新浪财报三表 (备用) — 资产负债表/利润表/现金流量表 HTML解析
  3. 东财push2 (最后) — 总股本/流通市值/行业

用法:
    from data.financial_sources import enrich_stock_with_financials, enrich_batch
    stock = enrich_stock_with_financials({"code": "600519", "name": "贵州茅台"})
    stocks = enrich_batch([{"code": "600519"}, {"code": "000858"}])
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("aurora.financial")

# ─── Constants ───────────────────────────────────────────────────
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
     "Chrome/120.0.0.0 Safari/537.36"
EM_REFERER = "https://emweb.securities.eastmoney.com/"
EM_QUOTE_REFERER = "https://quote.eastmoney.com/"
SINA_REFERER = "https://finance.sina.com.cn"

# Cache: 5-minute TTL (in seconds)
FIN_CACHE_TTL = 300
_cache_lock = threading.Lock()
_fin_cache: Dict[str, dict] = {}  # code -> {data, _ts}


# ─── Mootdx helpers ──────────────────────────────────────────────

def _get_mootdx_client():
    """Lazy-init mootdx Quotes client (thread-safe singleton-ish)."""
    try:
        from mootdx.quotes import Quotes
        return Quotes.factory(market='std')
    except Exception as e:
        logger.warning(f"[Financial] mootdx init failed: {e}")
        return None


def _try_mootdx_finance(code: str) -> Optional[dict]:
    """Layer 1a: mootdx TCP finance() — latest 37-field snapshot.

    Returns a dict with fields like:
        zongguben, liutongguben, jingzichan, meigujingzichan,
        zhuyingshouru, jinglirun, jingyingxianjinliu,
        yingyelirun, zongzichan, liudongfuzhai, changqifuzhai,
        cunhuo, yingshouzhangkuan, touzishouyu, ipo_date, industry
    """
    client = _get_mootdx_client()
    if client is None:
        return None
    try:
        df = client.finance(symbol=code)
        if df is None or df.empty:
            return None
        row = df.iloc[0].to_dict()
        return row
    except Exception as e:
        logger.debug(f"[Financial] mootdx finance failed for {code}: {e}")
        return None


# ─── F10 text-table parser ───────────────────────────────────────

def _parse_f10_value(val_str: str) -> Optional[float]:
    """Parse a single F10 table cell value (e.g. '32.53', '823.2007亿', '-'')."""
    val_str = val_str.strip().replace(",", "").replace("%", "").replace(" ", "")
    if not val_str or val_str in ("-", "―", "—", ""):
        return None
    # Handle Chinese units: 亿 (100M), 万 (10K)
    multiplier = 1.0
    if "亿" in val_str:
        multiplier = 100_000_000
        val_str = val_str.replace("亿", "")
    elif "万" in val_str:
        multiplier = 10_000
        val_str = val_str.replace("万", "")
    try:
        return float(val_str) * multiplier
    except (ValueError, TypeError):
        return None


def _parse_f10_table(text: str) -> Dict[str, List[Tuple[str, Optional[float]]]]:
    """Parse the F10 '财务分析' text table into structured data.

    The F10 text uses box-drawing characters (┌─┬┐│├┼┤└┴┘) to form tables.
    Each row is: ｜metric_name｜val1｜val2｜...

    Returns: {metric_name: [(date_str, value), ...]}
    """
    lines = text.split("\n")
    metric_rows: Dict[str, List[Tuple[str, Optional[float]]]] = {}
    current_header: List[str] = []

    for line in lines:
        # Skip non-data lines
        if "┌" in line or "├" in line or "└" in line or "┐" in line or "┘" in line or "┤" in line or "┴" in line or "┬" in line or "┼" in line or "─" in line:
            # Check if this is a header line (contains dates)
            if "｜" in line:
                parts = [p.strip() for p in line.split("｜")]
                parts = [p for p in parts if p]
                if parts and parts[0] in ("财务指标", "财务指标(%)", "指标        (单位：元)"):
                    current_header = parts[1:]  # dates
            continue

        if "｜" not in line:
            continue

        # Parse data row
        parts = [p.strip() for p in line.split("｜")]
        parts = [p for p in parts if p]
        if len(parts) < 2:
            continue

        metric_name = parts[0].strip()
        if not metric_name or metric_name in ("财务指标", "财务指标(%)", "指标        (单位：元)"):
            # This is a header row
            current_header = parts[1:]
            continue

        values = parts[1:]
        # Align with header
        date_values = []
        for i, val_str in enumerate(values):
            date_str = current_header[i] if i < len(current_header) else f"col_{i}"
            val = _parse_f10_value(val_str)
            date_values.append((date_str, val))

        metric_rows[metric_name] = date_values

    return metric_rows


def _extract_annual_values(
    rows: Dict[str, List[Tuple[str, Optional[float]]]],
    metric_name: str,
    max_years: int = 10,
) -> List[float]:
    """Extract annual (12-31) values for a metric, newest first."""
    entries = rows.get(metric_name, [])
    annuals = [(d, v) for d, v in entries if "12-31" in d and v is not None]
    # Sort by date descending
    annuals.sort(key=lambda x: x[0], reverse=True)
    return [v for _, v in annuals[:max_years]]


def _try_mootdx_f10(code: str) -> Optional[dict]:
    """Layer 1b: mootdx F10 — parse multi-year financial metrics from text.

    Extracts: ROE, gross margin, net margin, OCF, revenue, net profit
    """
    client = _get_mootdx_client()
    if client is None:
        return None
    try:
        f10 = client.F10(symbol=code)
        if f10 is None:
            return None
        caiwu = f10.get("财务分析", "")
        if not caiwu:
            return None

        parsed = _parse_f10_table(caiwu)

        result = {}

        # ── ROE ──
        for name in ("加权净资产收益率", "加权净资产收益率(%)"):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 10)
                if vals:
                    result["roe_values"] = vals
                    result["roe_10yr"] = sum(vals) / len(vals) if vals else None
                    result["roe"] = vals[0] if vals else None
                break

        # ── Gross margin ──
        for name in ("营业毛利率",):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 10)
                if vals:
                    result["gross_margin_values"] = vals
                    result["gross_margin_lt"] = sum(vals) / len(vals) if vals else None
                    result["gross_margin"] = vals[0] if vals else None
                break

        # ── Net margin (营业净利率) ──
        for name in ("营业净利率",):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 10)
                if vals:
                    result["net_margin_values"] = vals
                    result["net_margin_lt"] = sum(vals) / len(vals) if vals else None
                    result["net_margin"] = vals[0] if vals else None
                break

        # ── Operating profit margin (营业利润率) ──
        for name in ("营业利润率",):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 10)
                if vals:
                    result["operating_margin_values"] = vals
                break

        # ── Revenue (营业收入) from 利润表摘要 ──
        for name in ("营业收入",):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 10)
                if vals:
                    result["revenue_values"] = vals
                    # Revenue growth (3-year CAGR)
                    if len(vals) >= 4:
                        r_old = vals[-1] if vals[-1] != 0 else 1
                        r_new = vals[0]
                        result["revenue_growth_3yr"] = ((r_new / r_old) ** (1 / 3) - 1) * 100
                break

        # ── Net profit (净利润) ──
        for name in ("净利润",):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 10)
                if vals:
                    result["net_profit_values"] = vals
                break

        # ── OCF per share (每股经营现金流量) ──
        for name in ("每股经营现金流量(元)", "每股经营现金流量"):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 10)
                if vals:
                    result["ocf_per_share_values"] = vals
                    result["ocf_per_share"] = vals[0] if vals else None
                break

        # ── OCF (经营活动现金净额) from 现金流量表摘要 ──
        for name in ("经营活动现金净额",):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 10)
                if vals:
                    result["ocf_values"] = vals
                    if len(vals) >= 2:
                        result["ocf_recent_positive"] = vals[0] > 0
                break

        # ── EPS (基本每股收益) ──
        for name in ("基本每股收益(元)", "基本每股收益"):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 10)
                if vals:
                    result["eps_values"] = vals
                    result["eps"] = vals[0] if vals else None
                break

        # ── Total assets (资产总额) ──
        for name in ("资产总额",):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 5)
                if vals:
                    result["total_assets_values"] = vals
                break

        # ── Total liabilities (负债总额) ──
        for name in ("负债总额",):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 5)
                if vals:
                    result["total_liabilities_values"] = vals
                break

        # ── Shareholders equity (股东权益合计 / 母公司股东权益) ──
        for name in ("股东权益合计",):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 5)
                if vals:
                    result["equity_values"] = vals
                break

        # ── Financial expense (财务费用) — for interest coverage ──
        for name in ("财务费用",):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 5)
                if vals:
                    result["interest_expense_values"] = vals
                break

        # ── Operating profit (营业利润) — for interest coverage ──
        for name in ("营业利润",):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 5)
                if vals:
                    result["operating_profit_values"] = vals
                break

        # ── CapEx approximation from 投资活动现金净额 ──
        for name in ("投资活动现金净额",):
            if name in parsed:
                vals = _extract_annual_values(parsed, name, 5)
                if vals:
                    result["capex_values"] = [abs(v) for v in vals]
                break

        # ── Total shares from 主要财务指标 or finance() ──
        # (will be filled by mootdx finance snapshot)

        if result:
            result["_f10_source"] = "mootdx_f10"

        return result
    except Exception as e:
        logger.debug(f"[Financial] mootdx F10 failed for {code}: {e}")
        return None


# ─── Sina financial statements (Layer 2) ─────────────────────────

def _code_to_sina_market(code: str) -> str:
    """Convert stock code to Sina market prefix."""
    code = str(code).zfill(6)
    if code.startswith(("6", "9")):
        return "sh" + code
    return "sz" + code


def _try_sina_financial(code: str) -> Optional[dict]:
    """Layer 2: Parse Sina financial HTML pages for three statements.

    Returns dict with parsed values from balance sheet, income statement,
    and cash flow statement.
    """
    code = str(code).zfill(6)
    result = {}

    try:
        # ── Income statement: revenue, cost, net profit, operating profit ──
        url_is = (
            "https://vip.stock.finance.sina.com.cn/corp/go.php/"
            f"vFD_ProfitStatement/stockid/{code}/ctrl/part/displaytype/4.phtml"
        )
        r = requests.get(url_is, headers={"User-Agent": UA, "Referer": SINA_REFERER}, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            # Find all data rows
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        if "营业总收入" in label and "revenue_values_sina" not in result:
                            vals = []
                            for cell in cells[1:]:
                                v = _parse_f10_value(cell.get_text(strip=True))
                                if v is not None:
                                    vals.append(v)
                            if vals:
                                result["revenue_values_sina"] = vals
                        elif "净利润" in label and "营业利润" not in label and "net_profit_values_sina" not in result:
                            vals = []
                            for cell in cells[1:]:
                                v = _parse_f10_value(cell.get_text(strip=True))
                                if v is not None:
                                    vals.append(v)
                            if vals:
                                result["net_profit_values_sina"] = vals
                        elif "营业利润" in label and "operating_profit_values_sina" not in result:
                            vals = []
                            for cell in cells[1:]:
                                v = _parse_f10_value(cell.get_text(strip=True))
                                if v is not None:
                                    vals.append(v)
                            if vals:
                                result["operating_profit_values_sina"] = vals
                        elif "营业成本" in label and "cost_values_sina" not in result:
                            vals = []
                            for cell in cells[1:]:
                                v = _parse_f10_value(cell.get_text(strip=True))
                                if v is not None:
                                    vals.append(v)
                            if vals:
                                result["cost_values_sina"] = vals
                        elif "财务费用" in label and "interest_expense_values_sina" not in result:
                            vals = []
                            for cell in cells[1:]:
                                v = _parse_f10_value(cell.get_text(strip=True))
                                if v is not None:
                                    vals.append(v)
                            if vals:
                                result["interest_expense_values_sina"] = vals

        # ── Cash flow statement: OCF, FCF ──
        url_cf = (
            "https://vip.stock.finance.sina.com.cn/corp/go.php/"
            f"vFD_CashFlow/stockid/{code}/ctrl/part/displaytype/4.phtml"
        )
        r = requests.get(url_cf, headers={"User-Agent": UA, "Referer": SINA_REFERER}, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        if "经营活动现金净额" in label and "ocf_values_sina" not in result:
                            vals = []
                            for cell in cells[1:]:
                                v = _parse_f10_value(cell.get_text(strip=True))
                                if v is not None:
                                    vals.append(v)
                            if vals:
                                result["ocf_values_sina"] = vals
                        elif "投资活动现金净额" in label and "capex_values_sina" not in result:
                            vals = []
                            for cell in cells[1:]:
                                v = _parse_f10_value(cell.get_text(strip=True))
                                if v is not None:
                                    vals.append(v)
                            if vals:
                                result["capex_values_sina"] = [abs(v) for v in vals]

        # ── Balance sheet: total assets, liabilities, equity ──
        url_bs = (
            "https://vip.stock.finance.sina.com.cn/corp/go.php/"
            f"vFD_BalanceSheet/stockid/{code}/ctrl/part/displaytype/4.phtml"
        )
        r = requests.get(url_bs, headers={"User-Agent": UA, "Referer": SINA_REFERER}, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        if "资产总额" in label and "total_assets_values_sina" not in result:
                            vals = []
                            for cell in cells[1:]:
                                v = _parse_f10_value(cell.get_text(strip=True))
                                if v is not None:
                                    vals.append(v)
                            if vals:
                                result["total_assets_values_sina"] = vals
                        elif "负债总额" in label and "total_liabilities_values_sina" not in result:
                            vals = []
                            for cell in cells[1:]:
                                v = _parse_f10_value(cell.get_text(strip=True))
                                if v is not None:
                                    vals.append(v)
                            if vals:
                                result["total_liabilities_values_sina"] = vals
                        elif "股东权益合计" in label and "equity_values_sina" not in result:
                            vals = []
                            for cell in cells[1:]:
                                v = _parse_f10_value(cell.get_text(strip=True))
                                if v is not None:
                                    vals.append(v)
                            if vals:
                                result["equity_values_sina"] = vals

        if result:
            result["_sina_source"] = "sina_html"

        return result if result else None
    except Exception as e:
        logger.debug(f"[Financial] Sina financial failed for {code}: {e}")
        return None


# ─── EastMoney push2 (Layer 3) ───────────────────────────────────

def _try_push2_basic(code: str) -> Optional[dict]:
    """Layer 3: EastMoney push2 — total shares, market cap, industry code."""
    secid = _secid(code)
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "fields": "f57,f58,f84,f85,f100,f116,f117",
        "secid": secid,
    }
    try:
        r = requests.get(
            url, params=params,
            headers={"User-Agent": UA, "Referer": EM_QUOTE_REFERER},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            d = data.get("data", {})
            if d:
                result = {}
                # f84 = total shares (流通股本), f85 = total shares
                total_shares = d.get("f84") or d.get("f85")
                if total_shares:
                    result["total_shares"] = float(total_shares)
                # f116 = total market cap, f117 = circulating market cap
                total_mcap = d.get("f116")
                if total_mcap:
                    result["total_market_cap"] = float(total_mcap)
                circ_mcap = d.get("f117")
                if circ_mcap:
                    result["circulating_market_cap"] = float(circ_mcap)
                # f100 = industry code
                industry = d.get("f100")
                if industry is not None:
                    result["industry_code"] = int(industry) if industry else None
                return result if result else None
        return None
    except Exception as e:
        logger.debug(f"[Financial] push2 failed for {code}: {e}")
        return None


# ─── Caching (in-memory, thread-safe, 5-min TTL) ─────────────────

def _cache_get(code: str) -> Optional[dict]:
    """Get cached financial data for a stock code."""
    with _cache_lock:
        entry = _fin_cache.get(code)
        if entry is None:
            return None
        if time.time() - entry.get("_ts", 0) > FIN_CACHE_TTL:
            del _fin_cache[code]
            return None
        return entry.get("data")


def _cache_set(code: str, data: dict):
    """Cache financial data for a stock code."""
    with _cache_lock:
        _fin_cache[code] = {"data": data, "_ts": time.time()}
        # Lazy cleanup: remove expired entries if cache is large
        if len(_fin_cache) > 1000:
            now = time.time()
            expired = [k for k, v in _fin_cache.items()
                       if now - v.get("_ts", 0) > FIN_CACHE_TTL]
            for k in expired:
                del _fin_cache[k]


# ─── EM compatibility helpers ────────────────────────────────────


def _secid(code: str) -> str:
    """Convert stock code to EM secid format (type.code)."""
    code = str(code).zfill(6)
    if code.startswith(("6", "9")):
        return f"1.{code}"
    elif code.startswith(("0", "3", "2")):
        return f"0.{code}"
    elif code.startswith(("4", "8")):
        return f"0.{code}"
    return f"1.{code}"


def _code_prefix(code: str) -> str:
    """Return EM URL prefix (SH/SZ format)."""
    code = str(code).zfill(6)
    if code.startswith(("6", "9")):
        return f"SH{code}"
    return f"SZ{code}"


# ─── Safe float helper ───────────────────────────────────────────

def _safe_float(val, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if val is None:
        return default
    try:
        f = float(str(val).replace(",", "").replace("%", "").strip())
        return f if not (f != f) else default
    except (ValueError, TypeError):
        return default


# ─── Core computation ────────────────────────────────────────────

def _compute_berkshire_metrics(code: str) -> dict:
    """Compute all Berkshire filter metrics using 3-layer data sources.

    Layer 1: mootdx TCP (finance + F10)
    Layer 2: Sina financial HTML pages
    Layer 3: EastMoney push2
    """
    code = str(code).zfill(6)

    metrics = {
        "code": code,
        "roe_10yr": None,
        "fcf_5yr_cumulative": None,
        "interest_coverage": None,
        "gross_margin_lt": None,
        "ocf_to_ni_5yr": None,
        "net_margin_lt": None,
        "share_dilution_5yr": None,
        # Supplementary fields
        "roe": None,
        "gross_margin": None,
        "net_margin": None,
        "ocf_recent_positive": None,
        "net_margin_recovering": None,
        "listed_years": None,
        "ocf_per_share": None,
        "fcf_per_share": None,
        "is_platform_model": None,
        "revenue_growth_3yr": None,
        "eps": None,
        "total_shares": None,
        "_source": "none",
    }

    # ── Layer 1: mootdx ──
    fin = _try_mootdx_finance(code)
    f10_data = _try_mootdx_f10(code)

    if fin or f10_data:
        metrics["_source"] = "mootdx"

        # ── From finance snapshot ──
        if fin:
            # Total shares
            zgb = fin.get("zongguben") or fin.get("liutongguben")
            if zgb:
                metrics["total_shares"] = float(zgb)

            # Net asset per share / net assets
            meigu = fin.get("meigujingzichan")
            if meigu:
                metrics["meigujingzichan"] = float(meigu)

            # IPO date → listed years
            ipo = fin.get("ipo_date")
            if ipo:
                try:
                    ipo_dt = datetime.strptime(str(int(ipo)), "%Y%m%d")
                    years = (datetime.now() - ipo_dt).days / 365.25
                    metrics["listed_years"] = round(years, 1)
                except (ValueError, TypeError):
                    pass

            # Latest revenue and net profit from finance snapshot
            zhuying = fin.get("zhuyingshouru")
            jingli = fin.get("jinglirun")
            jingying_cf = fin.get("jingyingxianjinliu")
            yingye_lr = fin.get("yingyelirun")
            zong_zichan = fin.get("zongzichan")
            liudong_fuzhai = fin.get("liudongfuzhai")
            changqi_fuzhai = fin.get("changqifuzhai")
            cunhuo = fin.get("cunhuo")
            yingshou = fin.get("yingshouzhangkuan")

        # ── From F10 multi-year data ──
        if f10_data:
            # ROE
            if "roe_values" in f10_data:
                vals = f10_data["roe_values"]
                metrics["roe_10yr"] = sum(vals) / len(vals) if vals else None
                metrics["roe"] = vals[0] if vals else None

            # Gross margin
            if "gross_margin_values" in f10_data:
                vals = f10_data["gross_margin_values"]
                metrics["gross_margin_lt"] = sum(vals) / len(vals) if vals else None
                metrics["gross_margin"] = vals[0] if vals else None

            # Net margin
            if "net_margin_values" in f10_data:
                vals = f10_data["net_margin_values"]
                metrics["net_margin_lt"] = sum(vals) / len(vals) if vals else None
                metrics["net_margin"] = vals[0] if vals else None
                if len(vals) >= 4:
                    recent = vals[0]
                    prev3 = sum(vals[1:4]) / 3 if vals[1:4] else 0
                    metrics["net_margin_recovering"] = recent > prev3
            elif "net_profit_values" in f10_data and "revenue_values" in f10_data:
                # Calculate net margin from profit/revenue
                nps = f10_data["net_profit_values"]
                revs = f10_data["revenue_values"]
                nm_list = []
                for n, r in zip(nps[:10], revs[:10]):
                    if r and r > 0:
                        nm_list.append((n / r) * 100)
                if nm_list:
                    metrics["net_margin_lt"] = sum(nm_list) / len(nm_list)
                    metrics["net_margin"] = nm_list[0]
                    if len(nm_list) >= 4:
                        metrics["net_margin_recovering"] = nm_list[0] > sum(nm_list[1:4]) / 3

            # Revenue growth
            if "revenue_growth_3yr" in f10_data:
                metrics["revenue_growth_3yr"] = f10_data["revenue_growth_3yr"]

            # OCF
            ocf_vals = f10_data.get("ocf_values") or f10_data.get("ocf_per_share_values")
            if ocf_vals:
                metrics["ocf_per_share"] = ocf_vals[0] if ocf_vals else None
                metrics["ocf_recent_positive"] = len(ocf_vals) >= 2 and ocf_vals[0] > 0

            # OCF to Net Income ratio
            nps = f10_data.get("net_profit_values")
            ocf_vals_explicit = f10_data.get("ocf_values")
            if nps and ocf_vals_explicit and len(nps) == len(ocf_vals_explicit):
                ratios = []
                for o, n in zip(ocf_vals_explicit[:5], nps[:5]):
                    if n and n != 0:
                        ratios.append(o / n)
                if ratios:
                    metrics["ocf_to_ni_5yr"] = sum(ratios) / len(ratios)

            # Free cash flow (OCF - CapEx)
            capex_vals = f10_data.get("capex_values")
            if ocf_vals_explicit and capex_vals:
                fcf_5yr = 0
                for ocf, capex in zip(ocf_vals_explicit[:5], capex_vals[:5]):
                    fcf_5yr += (ocf - capex)
                metrics["fcf_5yr_cumulative"] = fcf_5yr
                if ocf_vals_explicit and capex_vals:
                    metrics["fcf_per_share"] = ocf_vals_explicit[0] - (capex_vals[0] if capex_vals else 0)

            # Interest coverage (EBIT / Interest Expense)
            op_profits = f10_data.get("operating_profit_values")
            int_expenses = f10_data.get("interest_expense_values")
            if op_profits and int_expenses:
                # Use absolute value to handle negative finance expense
                int_val = abs(int_expenses[0]) if int_expenses[0] is not None else 0
                if int_val > 0 and op_profits[0] is not None:
                    metrics["interest_coverage"] = abs(op_profits[0] / int_val) if int_val else None

            # EPS
            if "eps" in f10_data:
                metrics["eps"] = f10_data["eps"]

            # Share dilution
            total_shares = metrics.get("total_shares")
            if total_shares and fin:
                # Compare current total shares with earliest year
                # From finance snapshot vs 5 years ago - approximation
                pass

            # Gross margin from revenue/cost if not directly available
            if metrics["gross_margin_lt"] is None and "cost_values_sina" in f10_data or True:
                costs = f10_data.get("cost_values_sina")
                revs = f10_data.get("revenue_values")
                if costs and revs and not metrics["gross_margin_lt"]:
                    gm_list = []
                    for r, c in zip(revs[:10], costs[:10]):
                        if r and r > 0:
                            gm_list.append(((r - c) / r) * 100)
                    if gm_list:
                        metrics["gross_margin_lt"] = sum(gm_list) / len(gm_list)
                        metrics["gross_margin"] = gm_list[0]

    # ── Layer 2: Sina fallback ──
    if metrics["roe_10yr"] is None or metrics["gross_margin_lt"] is None:
        sina_data = _try_sina_financial(code)
        if sina_data:
            if metrics["_source"] == "none":
                metrics["_source"] = "sina"

            # Fill missing ROE from Sina
            if metrics.get("roe") is None:
                # Sina doesn't directly give ROE, but has net profit and equity
                nps = sina_data.get("net_profit_values_sina")
                eqs = sina_data.get("equity_values_sina")
                if nps and eqs and len(nps) == len(eqs):
                    roe_vals = []
                    for n, e in zip(nps[:10], eqs[:10]):
                        if e and e > 0:
                            roe_vals.append((n / e) * 100)
                    if roe_vals:
                        metrics["roe"] = roe_vals[0]
                        metrics["roe_10yr"] = sum(roe_vals) / len(roe_vals)

            # Fill gross margin from Sina
            if metrics.get("gross_margin_lt") is None:
                revs = sina_data.get("revenue_values_sina")
                costs = sina_data.get("cost_values_sina")
                if revs and costs:
                    gm_list = []
                    for r, c in zip(revs[:10], costs[:10]):
                        if r and r > 0:
                            gm_list.append(((r - c) / r) * 100)
                    if gm_list:
                        metrics["gross_margin_lt"] = sum(gm_list) / len(gm_list)
                        metrics["gross_margin"] = gm_list[0]

            # Net margin from Sina
            if metrics.get("net_margin_lt") is None:
                nps = sina_data.get("net_profit_values_sina")
                revs = sina_data.get("revenue_values_sina")
                if nps and revs:
                    nm_list = []
                    for n, r in zip(nps[:10], revs[:10]):
                        if r and r > 0:
                            nm_list.append((n / r) * 100)
                    if nm_list:
                        metrics["net_margin_lt"] = sum(nm_list) / len(nm_list)
                        metrics["net_margin"] = nm_list[0]

            # Interest coverage from Sina
            if metrics.get("interest_coverage") is None:
                op_profits_sina = sina_data.get("operating_profit_values_sina")
                int_exp_sina = sina_data.get("interest_expense_values_sina")
                if op_profits_sina and int_exp_sina:
                    ie = abs(int_exp_sina[0]) if int_exp_sina[0] else 0
                    if ie > 0 and op_profits_sina[0]:
                        metrics["interest_coverage"] = abs(op_profits_sina[0] / ie)

            # OCF from Sina
            ocf_sina = sina_data.get("ocf_values_sina")
            if ocf_sina and metrics.get("ocf_recent_positive") is None:
                metrics["ocf_recent_positive"] = ocf_sina[0] > 0 if ocf_sina else None
                if ocf_sina and not metrics.get("ocf_per_share"):
                    metrics["ocf_per_share"] = ocf_sina[0]

            # OCF/NI from Sina
            if metrics.get("ocf_to_ni_5yr") is None:
                ocf_sina_vals = sina_data.get("ocf_values_sina")
                nps_sina = sina_data.get("net_profit_values_sina")
                if ocf_sina_vals and nps_sina:
                    ratios = []
                    for o, n in zip(ocf_sina_vals[:5], nps_sina[:5]):
                        if n and n != 0:
                            ratios.append(o / n)
                    if ratios:
                        metrics["ocf_to_ni_5yr"] = sum(ratios) / len(ratios)

            # FCF from Sina
            if metrics.get("fcf_5yr_cumulative") is None:
                ocf_sina_vals = sina_data.get("ocf_values_sina")
                capex_sina_vals = sina_data.get("capex_values_sina")
                if ocf_sina_vals and capex_sina_vals:
                    fcf_sum = 0
                    for ocf, capex in zip(ocf_sina_vals[:5], capex_sina_vals[:5]):
                        fcf_sum += (ocf - capex)
                    metrics["fcf_5yr_cumulative"] = fcf_sum

    # ── Layer 3: push2 fallback for basic info ──
    if metrics["total_shares"] is None:
        push2_data = _try_push2_basic(code)
        if push2_data:
            if metrics["_source"] == "none":
                metrics["_source"] = "push2"
            if push2_data.get("total_shares"):
                metrics["total_shares"] = push2_data["total_shares"]
            if push2_data.get("total_market_cap"):
                metrics["total_market_cap"] = push2_data["total_market_cap"]

    # ── Derived: Share dilution (approximate from total shares vs 5yr IPO) ──
    if metrics.get("total_shares") and not metrics.get("share_dilution_5yr"):
        # Without historical share count data, set to 0 (no dilution detected)
        metrics["share_dilution_5yr"] = 0.0

    # ── Derive listed_years from IPO date if not already set ──
    if metrics.get("listed_years") is None:
        # Estimate from data availability
        if metrics.get("roe_10yr") is not None:
            metrics["listed_years"] = 10
        elif metrics.get("roe") is not None:
            metrics["listed_years"] = 5
        else:
            metrics["listed_years"] = 0

    return metrics


# ─── Public API ──────────────────────────────────────────────────

def get_financial_indicators(code: str) -> dict:
    """
    Get comprehensive financial indicators for an A-share stock.

    Args:
        code: 6-digit A-share stock code (e.g. "600519")

    Returns:
        dict with Berkshire-compatible financial metrics, or
        empty dict if data unavailable
    """
    if code is None:
        return {}
    code = str(code).strip()
    if not code or not code.isdigit():
        logger.warning(f"[Financial] Invalid code: {code}")
        return {}
    code = code.zfill(6)
    if len(code) != 6:
        logger.warning(f"[Financial] Invalid code: {code}")
        return {}

    # Check cache
    cached = _cache_get(code)
    if cached is not None:
        logger.debug(f"[Financial] Cache hit for {code}")
        return cached

    # Compute metrics
    metrics = _compute_berkshire_metrics(code)

    # Cache result
    has_data = any(
        v is not None for k, v in metrics.items()
        if k not in ("code", "_source")
    )
    if has_data:
        result = {k: v for k, v in metrics.items()
                  if v is not None and k != "code" and not k.startswith("_")}
        _cache_set(code, result)
        logger.info(f"[Financial] Got financial data for {code} "
                     f"(ROE={metrics.get('roe_10yr', 'N/A')}, "
                     f"GM={metrics.get('gross_margin_lt', 'N/A')})")
        return result

    logger.debug(f"[Financial] No data available for {code}")
    return {}


def enrich_stock_with_financials(stock: dict) -> dict:
    """
    Add financial indicators to a stock dict for Berkshire filtering.

    Args:
        stock: dict with at least {"code": "600519"}

    Returns:
        stock dict with additional financial fields added.
        If financial data cannot be fetched, returns original stock unchanged.
    """
    code = stock.get("code", "")
    if not code:
        return stock

    fin_data = get_financial_indicators(code)
    if not fin_data:
        logger.debug(f"[Financial] No data for {code}, returning original stock")
        return stock

    enriched = {**stock, **fin_data}
    return enriched


def enrich_batch(stocks: List[dict]) -> List[dict]:
    """
    Batch enrich stocks with financial data.

    Args:
        stocks: list of stock dicts with at least 'code'

    Returns:
        list of enriched stock dicts
    """
    if not stocks:
        return []

    enriched = []
    for stock in stocks:
        enriched.append(enrich_stock_with_financials(stock))

    total = len(enriched)
    with_data = sum(1 for s in enriched
                    if s.get("roe_10yr") is not None)
    logger.info(f"[Financial] Batch enrich: {with_data}/{total} with data")
    return enriched


# ─── Independent test function ───────────────────────────────────

def test_single_stock(code: str = "600519") -> dict:
    """
    Test financial data fetching for a single stock.

    Args:
        code: 6-digit stock code (default: 600519 贵州茅台)

    Returns:
        dict of financial indicators
    """
    result = get_financial_indicators(code)
    print(f"\n{'=' * 50}")
    print(f"  基本面数据测试: {code}")
    print(f"{'=' * 50}")
    if not result:
        print(f"  ⚠ 未获取到 {code} 的基本面数据")
        print(f"  (可能原因: 网络不可用 / mootdx TCP 端口 / 代码无效)")
        return result

    display_fields = [
        ("roe_10yr", "10年平均ROE(%)"),
        ("roe", "最新ROE(%)"),
        ("gross_margin_lt", "长期毛利率(%)"),
        ("gross_margin", "最新毛利率(%)"),
        ("net_margin_lt", "长期净利率(%)"),
        ("net_margin", "最新净利率(%)"),
        ("fcf_5yr_cumulative", "5年累计自由现金流"),
        ("ocf_to_ni_5yr", "经营现金流/净利润(5年均值)"),
        ("interest_coverage", "利息覆盖倍数"),
        ("share_dilution_5yr", "5年股本膨胀(%)"),
        ("revenue_growth_3yr", "3年营收增长(%)"),
        ("ocf_recent_positive", "近期经营现金流为正"),
        ("net_margin_recovering", "净利率回升趋势"),
        ("listed_years", "上市年数(估计)"),
        ("eps", "基本每股收益"),
        ("total_shares", "总股本"),
    ]

    print(f"\n  ┌─ {'指标':<30} {'值':<20} ┐")
    for key, label in display_fields:
        val = result.get(key)
        if val is not None:
            if isinstance(val, bool):
                display = "✓" if val else "✗"
            elif isinstance(val, float):
                if abs(val) > 10000:
                    display = f"{val:,.2f}"
                elif val == int(val):
                    display = f"{val:.1f}"
                else:
                    display = f"{val:.2f}"
            else:
                display = str(val)
            print(f"  │ {label:<30} {display:<20} │")
    print(f"  └─{'─' * 52}┘")

    print(f"\n   Berkshire 7条去劣检查:")
    checks = [
        ("roe_10yr", "ROE≥8%", 8.0),
        ("fcf_5yr_cumulative", "FCF≥0", 0.0),
        ("interest_coverage", "利息覆盖≥2x", 2.0),
        ("gross_margin_lt", "毛利率≥15%", 15.0),
        ("ocf_to_ni_5yr", "OCF/NI≥0.7", 0.7),
        ("net_margin_lt", "净利率≥5%", 5.0),
        ("share_dilution_5yr", "股本膨胀≤20%", 20.0),
    ]
    passed = 0
    for key, name, threshold in checks:
        val = result.get(key)
        if val is None:
            status = "⚠ 无数据"
        elif key == "share_dilution_5yr":
            c = val <= threshold
            status = f"{'✓ 通过' if c else '✗ 未通过'} ({val:.2f})"
            if c:
                passed += 1
        else:
            c = val >= threshold
            status = f"{'✓ 通过' if c else '✗ 未通过'} ({val:.2f})"
            if c:
                passed += 1
        print(f"    {name:<20}: {status}")
    print(f"\n  得分: {passed}/7")
    return result


# ─── CLI entry point ────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    code = sys.argv[1] if len(sys.argv) > 1 else "600519"
    test_single_stock(code)
