"""Tiered JSON cache for fetcher scripts.

TTL is differentiated by data volatility:
- Real-time quote (price/change_pct):        60s
- Intraday K-line / capital flow / sentiment: 5 min
- Daily aggregates (LHB, north-bound):       2 hours
- News:                                       1 hour
- Quarterly financials / valuation history:  24 hours
- Static metadata (industry, name):          7 days

Set env STOCK_NO_CACHE=1 to bypass cache entirely (force refresh).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

# Tiered TTL constants (seconds)
TTL_REALTIME    = 60          # 1 minute — price snapshot
TTL_INTRADAY    = 5 * 60      # 5 min — kline, fund flow, sentiment hot rank
TTL_HOURLY      = 60 * 60     # 1 hour — news
TTL_DAILY       = 2 * 60 * 60 # 2 hours — LHB, northbound, margin (after market close)
TTL_QUARTERLY   = 24 * 60 * 60       # 24 hours — financials, research reports
TTL_STATIC      = 7 * 24 * 60 * 60   # 7 days — industry classification

# Default TTL when caller doesn't specify
CACHE_TTL_SECONDS = TTL_INTRADAY

CACHE_ROOT = Path(".cache")
NO_CACHE = os.environ.get("STOCK_NO_CACHE") == "1"


def _cache_path(ticker: str, key: str) -> Path:
    h = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    safe_key = "".join(c if c.isalnum() or c in "._-" else "_" for c in key)[:60]
    return CACHE_ROOT / ticker / "api_cache" / f"{safe_key}__{h}.json"


def cached(ticker: str, key: str, fetch_fn: Callable[[], Any], ttl: int = CACHE_TTL_SECONDS) -> Any:
    """Return cached value if fresh, else call fetch_fn and store.
    Set STOCK_NO_CACHE=1 in the environment to force refresh.
    """
    path = _cache_path(ticker, key)
    now = time.time()

    if not NO_CACHE and path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if now - payload.get("_cached_at", 0) < ttl:
                return payload["data"]
        except (json.JSONDecodeError, KeyError):
            pass

    data = fetch_fn()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"_cached_at": now, "data": data, "_ttl": ttl}, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return data


_MARKET_CLOCKS = {
    "A": ("Asia/Shanghai", "XSHG", ((dt_time(9, 30), dt_time(11, 30)), (dt_time(13, 0), dt_time(15, 0)))),
    "H": ("Asia/Hong_Kong", "XHKG", ((dt_time(9, 30), dt_time(12, 0)), (dt_time(13, 0), dt_time(16, 0)))),
    "U": ("America/New_York", "XNYS", ((dt_time(9, 30), dt_time(16, 0)),)),
}


def market_status(market: str = "A", now: datetime | None = None) -> dict:
    """Return exchange-aware market status for A/H/US equities."""
    market = str(market or "A").upper()
    if market in ("US", "USA"):
        market = "U"
    timezone_name, calendar_name, sessions = _MARKET_CLOCKS.get(market, _MARKET_CLOCKS["A"])
    tz = ZoneInfo(timezone_name)
    if now is None:
        local_now = datetime.now(tz)
    elif now.tzinfo is None:
        local_now = now.replace(tzinfo=tz)
    else:
        local_now = now.astimezone(tz)
    weekday = local_now.weekday()
    t = local_now.time().replace(tzinfo=None)
    calendar_verified = False

    try:
        import pandas as pd
        import exchange_calendars as xcals

        calendar = xcals.get_calendar(calendar_name)
        session = pd.Timestamp(local_now.date())
        calendar_verified = True
        if not calendar.is_session(session):
            return {
                "is_open": False,
                "label": "已休市 (非交易日)",
                "now": local_now.isoformat(timespec="seconds"),
                "market": market,
                "timezone": timezone_name,
                "calendar_verified": True,
            }
    except (ImportError, ModuleNotFoundError, ValueError, TypeError):
        pass

    if weekday >= 5:
        label, is_open = "已收盘 (周末)", False
    elif any(start <= t < end for start, end in sessions):
        label, is_open = "交易中", True
    elif len(sessions) > 1 and sessions[0][1] <= t < sessions[1][0]:
        label, is_open = "午间休市", False
    elif t < sessions[0][0]:
        label, is_open = "未开盘", False
    else:
        label, is_open = "已收盘", False
    return {
        "is_open": is_open,
        "label": label,
        "now": local_now.isoformat(timespec="seconds"),
        "market": market,
        "timezone": timezone_name,
        "calendar_verified": calendar_verified,
    }


def write_task_output(ticker: str, task_name: str, data: dict) -> Path:
    """Write a task's final JSON to .cache/{ticker}/{task_name}.json"""
    # v3.9.x · raw_data 记录采集时的思考档位。
    # --from-modeling 复用缓存时必须让 profile 与采集时一致：命令行省略 --depth 时
    # get_profile() 会回落 medium，于是 lite 采的缓存被按 medium 的 20 维跑自查闸
    # → 误报 critical 并拒绝生成报告，而用户无从得知要补 --depth lite。
    if task_name == "raw_data" and isinstance(data, dict) and "_profile_depth" not in data:
        _depth = os.environ.get("UZI_DEPTH")
        if _depth in ("lite", "medium", "deep"):
            data = {**data, "_profile_depth": _depth}
    path = CACHE_ROOT / ticker / f"{task_name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def read_task_output(ticker: str, task_name: str) -> dict | None:
    path = CACHE_ROOT / ticker / f"{task_name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def require_task_output(ticker: str, task_name: str) -> dict:
    """Hard gate: raise if previous task hasn't run."""
    data = read_task_output(ticker, task_name)
    if data is None:
        raise RuntimeError(
            f"Gate failed: {task_name}.json missing for {ticker}. "
            f"Run the previous task first."
        )
    return data
