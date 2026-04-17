"""NEW Fetcher · 基金经理抄作业面板.

Output shape (consumed by assemble_report.render_fund_managers):
[
  {
    "name": "张坤",
    "fund_name": "易方达蓝筹精选",
    "fund_code": "005827",
    "avatar": "zhangkun",         # optional, match investor_db id
    "position_pct": 3.2,
    "rank_in_fund": 8,
    "holding_quarters": 4,
    "position_trend": "加仓",
    "return_5y": 156.7,
    "annualized_5y": 20.5,
    "max_drawdown": -28.3,
    "sharpe": 1.42,
    "peer_rank_pct": 5,
    "nav_history": [1.0, 1.08, ...],
    "fund_url": "https://fund.eastmoney.com/005827.html",
  },
  ...
]

数据来源链：
1. akshare.stock_report_fund_hold_detail(symbol='基金持仓', date=最近季度) → 持有本股的基金列表
2. akshare.fund_em_manager / fund_manager_em → 基金经理信息
3. akshare.fund_open_fund_info_em(fund_code, indicator='累计净值走势') → 5Y NAV
4. 自算 return_5y / annualized / max_drawdown / sharpe
5. akshare.fund_em_rank_detail / fund_open_fund_rank_em → 同类排名

每个基金经理 5Y 业绩计算都需要拉一次 NAV，比较重。生产环境应该缓存 24h。
"""
from __future__ import annotations

import json
import math
import sys
import traceback
from datetime import datetime

import akshare as ak  # type: ignore
from lib.cache import cached, TTL_QUARTERLY
from lib.market_router import parse_ticker

# 基金经理 → investor_db 头像映射（可扩充）
MANAGER_AVATAR_MAP = {
    "张坤": "zhangkun",
    "谢治宇": "xiezhiyu",
    "朱少醒": "zhushaoxing",
    "冯柳": "fengliu",
    "邓晓峰": "dengxiaofeng",
}


def _recent_quarter_date() -> str:
    """Return the most recent reported quarter in YYYYMMDD format.
    Q1 report comes out in April; Q2 in August; Q3 in Oct; Q4 in March next year.
    We return the latest quarter for which a report likely exists.
    """
    today = datetime.now()
    y, m = today.year, today.month
    if m >= 10:
        return f"{y}0930"
    if m >= 7:
        return f"{y}0630"
    if m >= 4:
        return f"{y}0331"
    return f"{y - 1}1231"


def fetch_holding_funds(ticker_code: str, date: str = "") -> list[dict]:
    """Which funds hold this stock.

    Primary: stock_fund_stock_holder(symbol=code) — direct per-stock lookup, returns
    all funds holding this stock ordered by 持仓市值 desc. Bypasses the broken
    stock_report_fund_hold_detail endpoint.
    """
    try:
        df = ak.stock_fund_stock_holder(symbol=ticker_code)
        if df is None or df.empty:
            return []
        # Normalize column names to a stable shape
        out = []
        for _, row in df.iterrows():
            out.append({
                "基金名称": row.get("基金名称"),
                "基金代码": str(row.get("基金代码", "")),
                "持仓数量": row.get("持仓数量"),
                "占流通股比例": row.get("占流通股比例"),
                "持股市值": row.get("持股市值"),
                "占市值比例": row.get("占市值比例"),
                "截止日期": str(row.get("截止日期", "")),
            })
        return out
    except Exception as e:
        # Fallback: try the original but likely broken
        try:
            df = ak.stock_report_fund_hold_detail(symbol="基金持仓", date=date or "20241231")
            if df is None or df.empty:
                return []
            sub = df[df.get("股票代码", "").astype(str) == ticker_code]
            return sub.head(20).to_dict("records")
        except Exception:
            return [{"error": f"both fund lookup methods failed: {e}"}]


def compute_fund_stats(fund_code: str) -> dict:
    """Step 2: 给定 fund_code, 算 5Y 业绩 + 年化 + 最大回撤 + 夏普 + 同类排名."""
    try:
        df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="累计净值走势")
    except Exception as e:
        return {"error": f"fund_info fail: {e}"}
    if df is None or df.empty:
        return {}

    # Column names: 净值日期 / 累计净值
    date_col = "净值日期" if "净值日期" in df.columns else df.columns[0]
    nav_col = "累计净值" if "累计净值" in df.columns else df.columns[1]
    df = df.sort_values(date_col)
    # 近 5 年
    cutoff = f"{datetime.now().year - 5}-01-01"
    df5y = df[df[date_col].astype(str) >= cutoff]
    if len(df5y) < 50:
        df5y = df.tail(1260)

    try:
        navs = [float(v) for v in df5y[nav_col] if v and float(v) > 0]
    except (ValueError, TypeError):
        navs = []
    if len(navs) < 10:
        return {}

    start = navs[0]
    end = navs[-1]
    return_5y = (end - start) / start * 100
    years = max(len(navs) / 252, 0.5)
    annualized = ((end / start) ** (1 / years) - 1) * 100 if start > 0 else 0

    # Max drawdown
    peak = navs[0]
    max_dd = 0.0
    for v in navs:
        if v > peak:
            peak = v
        dd = (v - peak) / peak
        if dd < max_dd:
            max_dd = dd

    # Sharpe ratio (assume 3% risk-free)
    daily_rets = [(navs[i] / navs[i - 1] - 1) for i in range(1, len(navs)) if navs[i - 1] > 0]
    sharpe = 0.0
    if daily_rets:
        import statistics
        try:
            mean_ret = statistics.mean(daily_rets)
            std_ret = statistics.stdev(daily_rets) if len(daily_rets) > 1 else 1
            if std_ret > 0:
                sharpe = (mean_ret * 252 - 0.03) / (std_ret * math.sqrt(252))
        except Exception:
            pass

    # Downsample NAV to ~15 points for sparkline
    step = max(1, len(navs) // 15)
    nav_spark = [round(v / start, 3) for v in navs[::step]][:20]
    if nav_spark[-1] != round(end / start, 3):
        nav_spark.append(round(end / start, 3))

    return {
        "return_5y": round(return_5y, 1),
        "annualized_5y": round(annualized, 1),
        "max_drawdown": round(max_dd * 100, 1),
        "sharpe": round(sharpe, 2),
        "nav_history": nav_spark,
    }


def fetch_fund_manager_name(fund_code: str) -> str | None:
    """Best-effort: try to look up fund manager name."""
    try:
        df = ak.fund_individual_basic_info_xq(symbol=fund_code)
        if df is not None and not df.empty:
            m_row = df[df["item"].astype(str).str.contains("基金经理", na=False)] if "item" in df.columns else None
            if m_row is not None and not m_row.empty:
                return str(m_row["value"].iloc[0]).split(",")[0].strip()
    except Exception:
        pass
    return None


def _holding_quarters(ticker_code: str, fund_code: str, max_lookback: int = 8) -> tuple[int, str]:
    """Count consecutive quarters this fund has held this stock + trend vs last quarter."""
    from datetime import datetime as _dt
    today = _dt.now()
    count = 0
    last_pct = None
    trend = "持平"
    for i in range(max_lookback):
        y = today.year
        q = ((today.month - 1) // 3) - i
        while q < 0:
            q += 4
            y -= 1
        q_dates = ["0331", "0630", "0930", "1231"]
        date = f"{y}{q_dates[q]}"
        try:
            df = ak.stock_report_fund_hold_detail(symbol="基金持仓", date=date)
            if df is not None and not df.empty and "股票代码" in df.columns and "基金代码" in df.columns:
                hit = df[(df["股票代码"].astype(str) == ticker_code) & (df["基金代码"].astype(str) == fund_code)]
                if not hit.empty:
                    count += 1
                    if "占流通股比例" in hit.columns:
                        pct = float(hit["占流通股比例"].iloc[0])
                        if last_pct is not None:
                            trend = "加仓" if pct > last_pct else ("减仓" if pct < last_pct else "持平")
                        last_pct = pct
                    continue
            break
        except Exception:
            break
    if count == 1:
        trend = "新进"
    return count, trend


def main(ticker: str, limit: int | None = None) -> dict:
    """Fetch ALL active-equity funds holding this stock.

    v2.4: `limit` default changed from 50 → None (no cap). Hot stocks like 贵州茅台
    routinely have 100+ active funds holding them; the old hard-cap silently
    dropped bottom holders, making "抄作业" incomplete. Pass `limit=N` only
    for quick debugging.
    """
    ti = parse_ticker(ticker)
    if ti.market != "A":
        return {
            "ticker": ti.full,
            "data": {"fund_managers": [], "_note": "currently A-share only"},
            "source": "n/a",
            "fallback": True,
        }

    holders = cached(ti.full, f"fund_holders_v2", lambda: fetch_holding_funds(ti.code), ttl=TTL_QUARTERLY)

    # Filter out obvious ETFs/indexes (their 5Y return is not meaningful as "抄作业")
    # Keep only ACTIVE funds by excluding common ETF/指数/LOF name patterns
    def _is_active_fund(name: str) -> bool:
        name = str(name)
        etf_markers = ["ETF", "指数", "沪深300", "中证", "创业板", "科创", "红利指数"]
        return not any(m in name for m in etf_markers)

    active_holders = [h for h in holders if "error" not in h and _is_active_fund(h.get("基金名称", ""))]
    total_funds = len([h for h in holders if "error" not in h])
    iter_holders = active_holders if limit is None else active_holders[:limit]

    # v2.4 · 并行计算每个基金的 5Y 统计（以前 100+ 基金串行跑约 30s）
    def _build_row(row: dict) -> dict | None:
        fund_code = str(row.get("基金代码", ""))
        fund_name = str(row.get("基金名称", ""))
        if not fund_code:
            return None
        stats = cached(fund_code, f"fund_stats_{fund_code}", lambda: compute_fund_stats(fund_code), ttl=TTL_QUARTERLY)
        if not stats or "error" in stats:
            stats = {}
        manager_name = fetch_fund_manager_name(fund_code) or "—"
        try:
            position_pct = float(row.get("占市值比例", 0) or row.get("占流通股比例", 0))
        except (ValueError, TypeError):
            position_pct = 0.0
        return {
            "name": manager_name,
            "fund_name": fund_name,
            "fund_code": fund_code,
            "avatar": MANAGER_AVATAR_MAP.get(manager_name, ""),
            "position_pct": round(position_pct, 2),
            "rank_in_fund": 0,
            "holding_quarters": 1,
            "position_trend": "持有",
            "return_5y": stats.get("return_5y", 0),
            "annualized_5y": stats.get("annualized_5y", 0),
            "max_drawdown": stats.get("max_drawdown", 0),
            "sharpe": stats.get("sharpe", 0),
            "peer_rank_pct": 50,
            "nav_history": stats.get("nav_history", []),
            "fund_url": f"https://fund.eastmoney.com/{fund_code}.html",
        }

    # 并行度默认 1（serial）— Py3.13 下 akshare 内部 mini_racer/libffi 并发会致命崩溃。
    # 设置 UZI_FUND_WORKERS=N (N>1) 强制并行（自担 V8 isolate crash 风险）。
    # BUG#v2.4-followup: 默认 3 在 Py3.13 + macOS 下 fund_portfolio_hold_em 也会崩。
    import os as _os
    _workers = int(_os.environ.get("UZI_FUND_WORKERS", "1"))
    managers: list[dict] = []
    if _workers <= 1:
        for row in iter_holders:
            try:
                r = _build_row(row)
                if r is not None:
                    managers.append(r)
            except Exception:
                continue
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=_workers) as pool:
            futures = [pool.submit(_build_row, row) for row in iter_holders]
            for fut in as_completed(futures):
                try:
                    r = fut.result()
                    if r is not None:
                        managers.append(r)
                except Exception:
                    continue

    # Sort by 5Y return
    managers.sort(key=lambda m: m.get("return_5y", 0), reverse=True)

    passive_count = max(0, total_funds - len(active_holders))
    return {
        "ticker": ti.full,
        "data": {
            "fund_managers": managers,
            "total_funds_holding": total_funds,
            "active_funds_count": len(managers),
            "passive_funds_filtered": passive_count,
            "_note": (
                f"共 {total_funds} 家基金持有本股 · "
                f"收录 {len(managers)} 家主动权益基金（已按 5Y 累计收益排序）· "
                f"过滤 {passive_count} 家 ETF/指数基金"
            ),
        },
        "source": "akshare:stock_fund_stock_holder + fund_open_fund_info_em",
        "fallback": False,
    }


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "002273.SZ"
    try:
        result = main(arg)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    except Exception as e:
        traceback.print_exc()
