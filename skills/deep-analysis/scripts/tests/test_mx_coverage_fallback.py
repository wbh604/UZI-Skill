"""MX fallback for coverage-critical fields when sina/baidu SSL fails.

Regression for local macOS / restricted-network runs where:
- stock_financial_analysis_indicator (sina) SSL-fails → roe_history missing
- stock_zh_valuation_baidu SSL-fails → pe_quantile / pb_quantile missing
- UZI_DISABLE_MINI_RACER=1 used to skip entire fetch_valuation → pe empty
  even when basic.pe_ttm was already available.

These tests mock MXClient · no network / no real MX_APIKEY required.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def _mx_table(name_map: dict, heads: list, series: dict) -> dict:
    """Minimal SEARCH_DATA envelope matching MX live shape."""
    table = {"headName": heads, **series}
    return {
        "success": True,
        "status": 0,
        "code": 0,
        "data": {
            "status": 0,
            "code": 0,
            "data": {
                "protocolType": "SEARCH_DATA",
                "searchDataResultDTO": {
                    "dataTableDTOList": [{
                        "code": "600519.SH",
                        "entityName": "贵州茅台(600519.SH)",
                        "table": table,
                        "rawTable": table,
                        "nameMap": name_map,
                    }],
                },
            },
        },
    }


def test_parse_mx_roe_series_prefers_annual():
    from fetch_financials import _parse_mx_roe_series

    payload = _mx_table(
        name_map={"roe": "净资产收益率ROE(加权)"},
        heads=["2026一季报", "2025年报", "2024年报", "2023年报"],
        series={"roe": ["10.57", "32.53", "36.02", "34.19"]},
    )
    parsed = _parse_mx_roe_series(payload)
    assert parsed["roe_history"] == [34.19, 36.02, 32.53]
    assert parsed["financial_years"] == ["2023", "2024", "2025"]
    assert parsed["roe"] == "32.5%"


def test_fetch_roe_history_via_mx_uses_client(monkeypatch):
    from fetch_financials import _fetch_roe_history_via_mx
    import fetch_financials as ff

    fake = MagicMock()
    fake.available = True
    fake.query.return_value = _mx_table(
        name_map={"roe": "净资产收益率ROE(加权)"},
        heads=["2025年报", "2024年报", "2023年报"],
        series={"roe": ["32.53", "36.02", "34.19"]},
    )

    class _Client:
        def __init__(self, *a, **k):
            pass

        available = True
        query = fake.query

    monkeypatch.setattr(ff, "_fetch_roe_history_via_mx", ff._fetch_roe_history_via_mx)
    monkeypatch.setitem(sys.modules, "lib.mx_api", MagicMock(MXClient=_Client))

    # Call through the real helper with patched MXClient import inside function
    import lib.mx_api as mx_mod
    monkeypatch.setattr(mx_mod, "MXClient", _Client)

    out = _fetch_roe_history_via_mx("600519", "贵州茅台")
    assert out.get("roe_history") == [34.19, 36.02, 32.53]
    assert out.get("_mx_roe_query")


def test_mx_latest_pct_reads_window_from_label():
    from fetch_valuation import _mx_latest_pct

    payload = _mx_table(
        name_map={"p": "3年市盈率历史百分位"},
        heads=["2026-07-30", "2026-07-29"],
        series={"p": ["32.78%", "17.63%"]},
    )
    val, window = _mx_latest_pct(payload, "市盈率")
    assert val == 32.78
    assert window == "3 年"


def test_main_safe_fills_coverage_fields(monkeypatch):
    from fetch_valuation import main_safe
    import fetch_valuation as fv
    import lib.data_sources as ds

    monkeypatch.setattr(ds, "fetch_basic", lambda ti: {"pe_ttm": 20.58, "pb": 6.3, "name": "贵州茅台"})

    def _fake_mx(code, name_hint="", basic=None):
        return {
            "_valuation_source": "basic+mx_api",
            "pe": str((basic or {}).get("pe_ttm")),
            "pb": str((basic or {}).get("pb")),
            "pe_quantile": "3 年 33 分位",
            "pb_quantile": "8%",
        }

    monkeypatch.setattr(fv, "_fetch_valuation_via_mx", _fake_mx)
    out = main_safe("600519")
    assert out["fallback"] is False
    assert out["data"]["pe"] == "20.58"
    assert "分位" in out["data"]["pe_quantile"]
    assert out["data"]["pb_quantile"].endswith("%")


def test_disable_miniracer_valuation_uses_main_safe(monkeypatch, tmp_path):
    """UZI_DISABLE_MINI_RACER=1 · valuation must NOT return empty skip stub."""
    import run_real_test as rrt

    monkeypatch.setenv("UZI_DISABLE_MINI_RACER", "1")
    monkeypatch.setattr(rrt, "_MINI_RACER_SENTINEL", tmp_path / "sentinel")

    called = {}

    def _safe(ticker):
        called["ticker"] = ticker
        return {
            "ticker": "600519.SH",
            "data": {"pe": "20.58", "pe_quantile": "3 年 33 分位", "pb_quantile": "8%"},
            "source": "basic+mx_api (mini_racer-safe)",
            "fallback": False,
        }

    monkeypatch.setattr("fetch_valuation.main_safe", _safe, raising=False)
    # run_fetcher imports inside function for valuation safe path
    import fetch_valuation as fv
    monkeypatch.setattr(fv, "main_safe", _safe)

    result = rrt.run_fetcher("fetch_valuation", ("600519",))
    assert result.get("fallback") is False
    assert result.get("data", {}).get("pe") == "20.58"
    assert "safe" in (result.get("source") or "") or called.get("ticker") == "600519"


def test_financial_health_via_mx(monkeypatch):
    from fetch_financials import _fetch_financial_health_via_mx
    import lib.mx_api as mx_mod

    class _Client:
        available = True

        def __init__(self, *a, **k):
            pass

        def query(self, q):
            return _mx_table(
                name_map={
                    "a": "流动比率",
                    "b": "资产负债率",
                    "c": "总资产净利率ROA",
                    "d": "净利润/营业总收入(销售净利率)",
                },
                heads=["2026一季报", "2025年报"],
                series={
                    "a": ["7.061", "5.09"],
                    "b": ["12.12%", "16.42%"],
                    "c": ["9.027%", "28.31%"],
                    "d": ["51.47%", "49.58%"],
                },
            )

    monkeypatch.setattr(mx_mod, "MXClient", _Client)
    health = _fetch_financial_health_via_mx("600519", "贵州茅台")
    assert health["current_ratio"] == 5.09
    assert health["debt_ratio"] == 16.42
    assert health["roic"] == 28.31
    assert health["net_margin_pct"] == 49.58
