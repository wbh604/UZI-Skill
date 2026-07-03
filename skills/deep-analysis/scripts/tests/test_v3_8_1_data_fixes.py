"""Regression tests for #82/#83 data-layer fixes."""

from pathlib import Path
import sys

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))


def test_fetch_basic_a_runs_known_industry_gate_after_chain_error(monkeypatch):
    from lib import data_sources as ds
    from lib.market_router import parse_ticker

    ti = parse_ticker("600036.SH")
    monkeypatch.setattr(ds, "_fetch_basic_a_inner", lambda _ti, _out: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(ds, "_fetch_price_tencent_qt", lambda *_a, **_k: {})
    monkeypatch.setattr(ds, "_fetch_a_share_basic_from_baostock", lambda *_a, **_k: {})
    monkeypatch.setattr(ds, "_fetch_a_share_name_from_ak_code_name", lambda *_a, **_k: {})

    out = ds._fetch_basic_a(ti)

    assert out["industry"] == "银行"
    assert "_basic_chain_err" in out


def test_fetch_peers_self_only_fallback_when_industry_missing(monkeypatch):
    import fetch_peers
    from lib.market_router import parse_ticker

    monkeypatch.setattr(fetch_peers.ds, "fetch_basic", lambda _ti: {
        "code": "600036.SH",
        "name": "招商银行",
        "pe_ttm": 6.0,
        "pb": 0.8,
        "industry": None,
    })

    out = fetch_peers.main("600036.SH")["data"]

    assert out["peer_table"][0]["code"] == "600036.SH"
    assert out["peer_table"][0]["is_self"] is True
    assert "行业缺失" in out["fallback_reason"]


def test_fetch_financials_yearly_ocf_history_and_ratio(monkeypatch):
    import fetch_financials
    from lib.market_router import parse_ticker

    monkeypatch.setattr(fetch_financials.ak, "stock_financial_abstract", lambda symbol: pd.DataFrame({
        "指标": ["营业总收入", "归属于母公司所有者的净利润"],
        "20211231": [10e8, 1e8],
        "20221231": [12e8, 2e8],
    }))
    monkeypatch.setattr(fetch_financials.ak, "stock_financial_analysis_indicator", lambda symbol, start_year: pd.DataFrame())
    monkeypatch.setattr(fetch_financials.ak, "stock_history_dividend_detail", lambda symbol, indicator: pd.DataFrame())
    monkeypatch.setattr(fetch_financials.ak, "stock_cash_flow_sheet_by_quarterly_em", lambda symbol: (_ for _ in ()).throw(AssertionError("quarterly should not run")))

    cf = pd.DataFrame({
        "REPORT_DATE": ["2022-12-31", "2020-12-31", "2021-12-31"],
        "经营活动产生的现金流量净额": [3e8, 1e8, 2e8],
    })
    monkeypatch.setattr(fetch_financials.ak, "stock_cash_flow_sheet_by_yearly_em", lambda symbol: cf)

    ti = parse_ticker("002600.SZ")
    out = fetch_financials._fetch_a_share(ti)

    assert out["ocf_history"] == [1.0, 2.0, 3.0]
    assert out["ocf"] == "3.0亿"
    assert "fcf" not in out


def test_fetch_financials_quarterly_ocf_fallback_and_ratio(monkeypatch):
    import fetch_financials
    from lib.market_router import parse_ticker

    monkeypatch.setattr(fetch_financials.ak, "stock_financial_abstract", lambda symbol: pd.DataFrame({
        "指标": ["营业总收入", "归属于母公司所有者的净利润"],
        "20211231": [10e8, 1e8],
        "20221231": [12e8, 2e8],
    }))
    monkeypatch.setattr(fetch_financials.ak, "stock_financial_analysis_indicator", lambda symbol, start_year: pd.DataFrame())
    monkeypatch.setattr(fetch_financials.ak, "stock_history_dividend_detail", lambda symbol, indicator: pd.DataFrame())
    monkeypatch.setattr(fetch_financials.ak, "stock_cash_flow_sheet_by_yearly_em", lambda symbol: (_ for _ in ()).throw(RuntimeError("yearly down")))
    monkeypatch.setattr(fetch_financials.ak, "stock_cash_flow_sheet_by_quarterly_em", lambda symbol: pd.DataFrame({
        "REPORT_DATE": ["2022-03-31", "2022-06-30"],
        "NETCASH_OPERATE": [0.5e8, 1.5e8],
    }))

    ti = parse_ticker("002600.SZ")
    out = fetch_financials._fetch_a_share(ti)

    assert out["ocf_history"] == [0.5, 1.5]
    assert out["financial_health"]["ocf_to_ni"] == 75.0
    assert "_ocf_err" in out


def test_stock_features_exposes_ocf_keys_only():
    from lib.stock_features import extract_features

    raw = {
        "ticker": "600036.SH",
        "dimensions": {
            "1_financials": {"data": {"financial_health": {"ocf_to_ni": 125}}},
        },
    }

    f = extract_features(raw, raw["dimensions"])

    assert f["ocf_to_ni"] == 125
    assert f["ocf_positive"] is True
    assert f["ocf_to_net_income_ratio"] == 1.25
    assert "fcf_margin" not in f
    assert "fcf_positive" not in f
