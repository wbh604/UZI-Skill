from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def test_data_quality_tags_fields_and_reports_counts():
    from lib.data_quality import DataQuality, build_quality_report, mark_field, unwrap

    fields = {
        "pe": mark_field(18.2, DataQuality.ACTUAL, "eastmoney"),
        "pe_percentile": mark_field(42.0, DataQuality.DERIVED, "history"),
        "flow_trend": mark_field("加速流入", DataQuality.ESTIMATED, "volume_price"),
        "interest_expense": mark_field(None, DataQuality.UNAVAILABLE, "", "source missing"),
    }

    assert unwrap(fields["pe"]) == 18.2
    report = build_quality_report(fields)
    assert report["actual_count"] == 1
    assert report["derived_count"] == 1
    assert report["estimated_fields"] == ["flow_trend"]
    assert report["unavailable_fields"] == ["interest_expense"]
    assert report["overall_quality"] == "medium"


def test_registry_health_snapshot_orders_sources_by_dim_and_market():
    from lib.data_source_registry import source_health_snapshot

    snap = source_health_snapshot("10_valuation", "A")

    assert snap["dim"] == "10_valuation"
    assert snap["market"] == "A"
    assert snap["counts"]["total"] >= 1
    assert snap["sources"][0]["health"] in {"known_good", "flaky", "blocked_often", "needs_browser"}
    assert any(s["id"] == "em_valuation_history" for s in snap["sources"])


def test_eastmoney_valuation_history_normalizes_rows(monkeypatch):
    import fetch_valuation

    payload = {
        "result": {
            "data": [
                {"TRADE_DATE": "2026-01-03", "PE_TTM": "30", "PB_MRQ": "4.1"},
                {"TRADE_DATE": "2026-01-01", "PE_TTM": "20", "PB_MRQ": "3.9"},
                {"TRADE_DATE": "2026-01-02", "PE_TTM": "25", "PB_MRQ": "4.0"},
            ]
        }
    }

    monkeypatch.setattr(fetch_valuation, "_http_get_json", lambda url, headers=None, timeout=8: payload)
    hist = fetch_valuation._fetch_eastmoney_valuation_history("600519", history_len=250)

    assert hist["pe_history"] == [20.0, 25.0, 30.0]
    assert hist["pb_history"] == [3.9, 4.0, 4.1]
    assert hist["history_dates"] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert hist["source"] == "eastmoney:RPT_VALUEANALYSIS_DET"


def test_capital_flow_marks_main_flow_quality():
    from fetch_capital_flow import _main_flow_quality

    assert _main_flow_quality([{"主力净流入": 123.0}]) == {
        "value": "actual",
        "quality": "actual",
        "source": "akshare:stock_individual_fund_flow",
        "note": "",
    }
    assert _main_flow_quality([])["quality"] == "unavailable"
