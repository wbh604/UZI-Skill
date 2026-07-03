from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def test_quick_mode_fetches_individual_main_flow(monkeypatch):
    """Quick mode should fetch per-stock main fund flow; heavy only gates universe datasets."""
    import fetch_capital_flow as fcf

    monkeypatch.delenv("UZI_CAPITAL_FLOW_HEAVY", raising=False)
    calls = {}

    def fake_fund_flow(stock, market):
        calls["fund_flow"] = (stock, market)
        return pd.DataFrame([
            {"date": "2026-07-01", "主力净流入-净额": 100000000},
            {"date": "2026-07-02", "主力净流入-净额": -20000000},
        ])

    def fail_universe(*args, **kwargs):
        raise AssertionError("quick mode must not call universe-heavy fetchers")

    monkeypatch.setattr(fcf.ak, "stock_individual_fund_flow", fake_fund_flow)
    monkeypatch.setattr(fcf, "_universe_dzjy", fail_universe)
    monkeypatch.setattr(fcf, "_universe_release_summary", fail_universe)
    monkeypatch.setattr(fcf, "_universe_release_detail", fail_universe)
    monkeypatch.setattr(fcf, "_universe_margin_detail", fail_universe)

    result = fcf.main("600036.SH")
    data = result["data"]

    assert calls["fund_flow"] == ("600036", "sh")
    # quick mode 不应使用旧的 _skipped_heavy 整体跳过标记（会让下游误判资金面全空）;
    # 只允许 _skipped_universe_heavy（仅大宗/解禁等全市场慢接口跳过，个股资金流仍跑）
    assert "_skipped_heavy" not in data, "quick mode 不应用整体 _skipped_heavy 标记"
    assert len(data["main_fund_flow_20d"]) == 2
    assert data["main_20d"] != "—"
    assert data["main_5d"] != "—"
