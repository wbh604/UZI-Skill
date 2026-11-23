from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fetch_kline
from lib import data_sources as ds
from lib import cache
from lib.kline_quality import clean_kline_rows, usable_kline_snapshot
from lib.market_router import parse_ticker


def bar(index=0):
    return {"Date": f"fixture-{index}", "Open": 12, "Close": 13, "High": 14, "Low": 11, "Volume": 100}


@pytest.mark.parametrize("value", [None, "NaN", float("nan"), float("inf"), "bad", 0])
def test_partial_invalid_prices_drop_even_if_close_is_valid(value):
    source = [bar(), {**bar(1), "Low": value}, bar(2)]
    rows = clean_kline_rows(source)
    assert [row["Date"] for row in rows] == ["fixture-0", "fixture-2"]


def test_both_cache_reads_and_writes_are_normalized(monkeypatch):
    ti = parse_ticker("09626.HK")
    source = [bar(), {"日期": "bad", **{key: float("nan") for key in ("开盘", "收盘", "最高", "最低")}}]
    monkeypatch.setattr(ds, "_fetch_kline_impl", lambda *args: source)

    def fake_cached(ticker, key, fetch, ttl):
        assert ticker == ti.full and ttl == 300
        assert len(fetch()) == 1
        return source  # Simulate an old cache hit containing non-standard JSON values.

    monkeypatch.setattr(ds, "cached", fake_cached)
    rows = ds.fetch_kline(ti)
    assert len(rows) == 1 and rows[0]["收盘"] == 13
    json.dumps(rows, allow_nan=False)


def test_real_fresh_cache_is_filtered_without_deleting_or_refetching(tmp_path, monkeypatch):
    ti = parse_ticker("09626.HK")
    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(cache, "NO_CACHE", False)
    path = cache._cache_path(ti.full, "kline__9626__daily__20240101__qfq")
    path.parent.mkdir(parents=True)
    source = json.dumps({"_cached_at": time.time(), "data": [bar(), {**bar(1), "Close": float("nan")}]})
    path.write_text(source, encoding="utf-8")
    monkeypatch.setattr(ds, "_fetch_kline_impl", lambda *args: pytest.fail("Fresh cache must not refetch"))
    assert len(ds.fetch_kline(ti)) == 1
    assert path.read_text(encoding="utf-8") == source


@pytest.mark.parametrize(("ticker", "chain", "primary", "secondary"), [
    ("09626.HK", ds._kline_hk_chain, "stock_hk_hist", "stock_hk_daily"),
    ("600519.SH", ds._kline_a_share_chain, "stock_zh_a_hist", "stock_zh_a_daily"),
])
def test_all_bad_primary_rows_try_secondary(monkeypatch, ticker, chain, primary, secondary):
    result = pd.DataFrame([{"date": "2026-11-20", "open": 10, "close": 11, "low": 9, "high": 12}])
    monkeypatch.setattr(ds, "ak", SimpleNamespace(**{
        primary: lambda **_: pd.DataFrame([{"最低": float("nan")}]),
        secondary: lambda **_: result,
    }))
    monkeypatch.setattr(ds, "_retry", lambda callback, **_: callback())
    rows = chain(parse_ticker(ticker), "daily", "20240101", "qfq")
    assert len(rows) == 1 and rows[0]["收盘"] == 11


def test_us_uses_secondary_after_invalid_yfinance_rows(monkeypatch):
    ticker = SimpleNamespace(history=lambda **_: pd.DataFrame([{**bar(), "High": float("nan")}]))
    monkeypatch.setattr(ds, "yf", SimpleNamespace(Ticker=lambda _: ticker))
    monkeypatch.setattr(ds, "ak", SimpleNamespace(stock_us_hist=lambda **_: pd.DataFrame([bar()])))
    monkeypatch.setattr(ds, "_retry", lambda callback, **_: callback())
    rows = ds._kline_us_chain(parse_ticker("AAPL"))
    assert len(rows) == 1 and rows[0]["收盘"] == 13


def test_valid_prices_still_render_when_volume_missing(monkeypatch):
    source = [bar(i) for i in range(22)]
    source[-1]["Volume"] = float("nan")
    source.insert(10, {**bar(-1), "Open": float("nan"), "Close": float("nan")})
    monkeypatch.setattr(ds, "fetch_kline", lambda *args: source)
    monkeypatch.setattr(fetch_kline, "fetch_chip_distribution", lambda _: {})
    data = fetch_kline.main("09626.HK")["data"]
    assert data["kline_count"] == 22 and len(data["candles_60d"]) == 22
    assert data["indicators"]["last_close"] == 13
    assert data["indicators"]["obv"] is None
    assert data["indicators"]["vol_5_vs_20"] is None
    assert usable_kline_snapshot(data)
    json.dumps(data, allow_nan=False)
    bad = deepcopy(data)
    bad["ma20_60d"][-1] = float("nan")
    assert not usable_kline_snapshot(bad)
    bad = deepcopy(data)
    bad["kline_stats"]["volatility"] = "nan%"
    assert not usable_kline_snapshot(bad)


def test_source_error_is_not_a_single_fake_candle(monkeypatch):
    monkeypatch.setattr(ds, "fetch_kline", lambda *args: [{"_kline_fetch_error": "synthetic failure"}])
    result = fetch_kline.main("09626.HK")
    assert result["data"] == {} and result["error"] == "synthetic failure"
