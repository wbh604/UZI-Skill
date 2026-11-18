"""Provider-specific history must never masquerade as score input."""
from datetime import date
from io import BytesIO
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fetch_capital_flow as fetcher
from lib.capital_flow_history import MAIN_NET, window_net
from lib.market_router import parse_ticker
from lib.pipeline.score_fns import score_dimensions
from lib.report.dim_viz import _viz_capital_flow
from lib.self_review import check_empty_dims
from lib.stock_features import extract_features


TODAY = date(2026, 11, 18)


def sina_row(day, r0="10", r1="-3"):
    return {"opendate": day, "r0_net": r0, "r1_net": r1, "turnover": "0.27", "netamount": "99"}


def stub_sina(monkeypatch, payload, expected="sh600519"):
    def open_payload(request, *, timeout):
        parts = urlsplit(request.full_url)
        assert parts.hostname == "vip.stock.finance.sina.com.cn"
        assert parts.path.endswith("MoneyFlow.ssl_qsfx_lscjfb")
        assert parse_qs(parts.query)["daima"] == [expected]
        assert timeout == 8
        return BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(fetcher, "urlopen", open_payload)


def test_eastmoney_preferred_and_recent_window_used(monkeypatch):
    days = [date(2026, 11, n) for n in (10, 11, 12, 13, 16, 17)]
    rows = [{"日期": day, MAIN_NET: value} for day, value in zip(days, [-200, 1, 2, 3, 4, 5])]
    monkeypatch.setattr(fetcher.ak, "stock_individual_fund_flow", lambda **_: pd.DataFrame(rows), raising=False)
    monkeypatch.setattr(fetcher, "urlopen", lambda *_, **__: pytest.fail("Unexpected fallback"))
    result = fetcher._fetch_main_flow(parse_ticker("600519.SH"), TODAY)
    assert result["main_flow_source"] == "akshare:eastmoney"
    assert result["main_flow_error"] is None
    assert window_net(result["main_fund_flow_20d"], 5) == 15
    assert window_net(rows, 5) == 15  # Pre-update cache in ascending order.


def test_renamed_akshare_endpoint_still_uses_eastmoney_first(monkeypatch):
    monkeypatch.delattr(fetcher.ak, "stock_individual_fund_flow", raising=False)

    def new_endpoint(*, symbol, market):
        assert (symbol, market) == ("920001", "bj")
        return pd.DataFrame([{"日期": "2026-11-17", MAIN_NET: 0.0}])

    monkeypatch.setattr(fetcher.ak, "stock_fund_flow_individual_hist_em", new_endpoint, raising=False)
    monkeypatch.setattr(fetcher, "urlopen", lambda *_, **__: pytest.fail("Unexpected fallback"))
    result = fetcher._fetch_main_flow(parse_ticker("920001.BJ"), TODAY)
    assert result["main_flow_source"] == "akshare:eastmoney"
    assert result["main_fund_flow_20d"][0][MAIN_NET] == 0


@pytest.mark.parametrize(("ticker", "symbol"), [
    ("600519.SH", "sh600519"), ("301377.SZ", "sz301377"), ("920001.BJ", "bj920001"),
])
def test_sina_observation_uses_exchange_and_not_turnover(monkeypatch, ticker, symbol):
    monkeypatch.setattr(fetcher.ak, "stock_individual_fund_flow", lambda **_: pd.DataFrame(), raising=False)
    stub_sina(monkeypatch, [
        sina_row("2026-11-13"),
        sina_row("2026-11-18"),
        sina_row("2026-11-17", "0", "0"),
        sina_row("2026-11-17", "0.00", "0"),
        sina_row("2026-11-16", "9", None),
        sina_row("2026-11-19"),
    ], expected=symbol)
    result = fetcher._fetch_main_flow(parse_ticker(ticker), TODAY)
    assert not result["main_fund_flow_20d"]
    assert result["main_flow_source"] is None
    assert "no recent valid" in result["main_flow_error"]
    obs = result["sina_flow_observation"]
    assert obs["currency"] == "CNY"
    assert obs["latest_valid_date"] == "2026-11-17"
    assert obs["rows"] == [
        {"date": "2026-11-17", "large_order_net_cny": 0},
        {"date": "2026-11-16", "large_order_net_cny": None},
        {"date": "2026-11-13", "large_order_net_cny": 7},
    ]
    assert obs["net_5_rows_cny"] is None


def test_conflicting_duplicate_invalidates_window_but_not_observation(monkeypatch):
    rows = [sina_row(f"2026-11-{n}") for n in (11, 12, 13, 16, 17)]
    stub_sina(monkeypatch, rows + [sina_row("2026-11-16", "19")])
    result = fetcher._fetch_sina_observation("sh600519", TODAY)
    assert result["rows"][1]["large_order_net_cny"] is None
    assert result["net_5_rows_cny"] is None
    stub_sina(monkeypatch, rows)
    assert fetcher._fetch_sina_observation("sh600519", TODAY)["net_5_rows_cny"] == 35


@pytest.mark.parametrize("payload", [
    [], None, {"error": "invalid"}, [sina_row("2026-10-19")],
    [sina_row("2026-11-17", "NaN")], [sina_row("2026-11-17", r1=True)],
    [sina_row("2026-11-17", r1="Infinity")], [{"opendate": "2026-11-17", "r0_net": 10}],
])
def test_two_source_failures_report_missing_without_fake_zero(monkeypatch, payload):
    def fail(**_):
        raise ConnectionError("synthetic outage")
    monkeypatch.setattr(fetcher.ak, "stock_individual_fund_flow", fail, raising=False)
    stub_sina(monkeypatch, payload)
    result = fetcher._fetch_main_flow(parse_ticker("600519.SH"), TODAY)
    assert result["main_flow_error"] == "Eastmoney fetch failed (ConnectionError)"
    assert result["sina_flow_error"]
    assert result["sina_flow_observation"] is None
    assert result["main_fund_flow_20d"] == []


def test_inconsistent_exchange_is_rejected_without_network(monkeypatch):
    monkeypatch.setattr(fetcher.ak, "stock_individual_fund_flow", lambda **_: pytest.fail("Unexpected fetch"), raising=False)
    monkeypatch.setattr(fetcher, "urlopen", lambda *_, **__: pytest.fail("Unexpected fetch"))
    result = fetcher._fetch_main_flow(parse_ticker("000001.SH"), TODAY)
    assert "inconsistent" in result["main_flow_error"]


def test_sina_observation_visible_and_never_used_for_scoring(monkeypatch):
    stub_sina(monkeypatch, [
        sina_row(f"2026-11-{n}", "200000000", "0") for n in (11, 12, 13, 16, 17)
    ])
    obs = fetcher._fetch_sina_observation("sh600519", TODAY)
    cap = {"main_flow_error": "unavailable", "main_fund_flow_20d": [], "sina_flow_observation": obs}
    dims = {"12_capital_flow": {"data": cap}}
    raw = {"ticker": "600519.SH", "market": "A", "dimensions": dims}
    score = score_dimensions(raw)["dimensions"]["12_capital_flow"]
    assert "数据暂缺" in score["label"]
    assert score["reasons_pass"] == score["reasons_fail"] == []
    assert extract_features(raw, dims)["main_fund_5d_net_yi"] is None
    issues = check_empty_dims({"dims": dims})
    assert len(issues) == 1 and issues[0].severity == "warning"
    html = _viz_capital_flow(cap)
    assert "新浪历史成交分布（仅观察，不参与评分）" in html
    assert "10.00 亿元" in html


@pytest.mark.parametrize("values,expected", [([0] * 5, 0), ([1] * 4, None), ([1, 2, None, 3, 4], None)])
def test_window_requires_complete_finite_values(values, expected):
    assert window_net([{MAIN_NET: value} for value in values], 5) == expected


def test_report_chart_is_identical_for_old_and_new_cache_order():
    history = [{"日期": f"2026-11-{day}", MAIN_NET: amount}
               for day, amount in zip((11, 12, 13, 16, 17), (-3, 5, -1, 10, 2))]
    assert _viz_capital_flow({"main_fund_flow_20d": history}) == _viz_capital_flow({
        "main_fund_flow_20d": list(reversed(history)),
    })
