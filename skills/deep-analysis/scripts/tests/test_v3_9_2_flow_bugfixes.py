"""Regression tests for flow and data-contract bug fixes."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

SCRIPTS = Path(__file__).resolve().parent.parent
ROOT = SCRIPTS.parent.parent.parent
sys.path.insert(0, str(SCRIPTS))


def _load_root_run_module():
    spec = importlib.util.spec_from_file_location("uzi_root_run_for_tests", ROOT / "run.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    old_cwd = Path.cwd()
    try:
        spec.loader.exec_module(mod)
    finally:
        # run.py changes cwd on import; keep pytest cwd stable for later tests.
        import os
        os.chdir(old_cwd)
    return mod


def test_direct_report_path_takes_precedence_for_fund_summary(tmp_path):
    """Fund/versus/portfolio reports must reuse the generated HTML path."""
    mod = _load_root_run_module()
    summary = tmp_path / "fund-summary.html"
    summary.write_text("<html>summary</html>", encoding="utf-8")
    args = SimpleNamespace(_direct_report_path=summary)

    report_dir, standalone = mod._resolve_report_artifact(args, mod.SCRIPTS_DIR, "510300.SH")

    assert standalone == summary
    assert report_dir == tmp_path


def test_cloudflare_tunnel_does_not_auto_install_without_opt_in(monkeypatch):
    """--remote should not install packages or call sudo unless explicitly requested."""
    mod = _load_root_run_module()
    calls = []

    monkeypatch.setattr(mod.shutil, "which", lambda _name: None)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw: calls.append((a, kw)))

    public_url, proc = mod.start_cloudflare_tunnel(8976, install=False)

    assert public_url is None
    assert proc is None
    assert calls == []


def test_agent_analysis_errors_fall_back_to_script_stub():
    """Structural agent_analysis errors must be discarded before synthesis merge."""
    import run_real_test as rrt

    bad = {"agent_reviewed": True, "dim_commentary": ["bad"], "narrative_override": ["bad"]}
    cleaned, issues = rrt._validate_agent_analysis_or_fallback(bad, "600519.SH")

    assert cleaned is None
    assert any(i.severity == "error" for i in issues)


def test_financials_exposes_ocf_fields():
    """Operating cash flow must not be hidden behind the fcf field only."""
    import fetch_financials as ff

    out = {"net_profit_history": [10.0]}
    df_cf = pd.DataFrame({"经营活动产生的现金流量净额": [12e8, 8e8]})

    ff._apply_operating_cash_flow(out, df_cf)

    assert out["ocf"] == "12.0亿"
    assert out["operating_cash_flow_yi"] == 12.0
    assert out["ocf_history"] == [12.0, 8.0]
    assert out["ocf_to_net_income_ratio"] == 1.2
    assert out["financial_health"]["ocf_to_net_income_ratio"] == 1.2


def test_stock_features_reads_ocf_to_net_income_ratio():
    from lib.stock_features import extract_features

    raw = {
        "ticker": "TEST",
        "market": "A",
        "dimensions": {
            "0_basic": {"data": {"name": "测试", "price": 10, "market_cap_yi": 100}},
            "1_financials": {"data": {
                "net_profit_history": [10.0],
                "revenue_history": [100.0],
                "ocf_to_net_income_ratio": 0.42,
                "financial_health": {"debt_ratio": 20, "current_ratio": 2},
            }},
        },
    }

    features = extract_features(raw, raw["dimensions"])

    assert features["ocf_to_net_income_ratio"] == 0.42


def test_peers_self_only_fallback_when_industry_missing(monkeypatch):
    import fetch_peers

    monkeypatch.setattr(fetch_peers.ds, "fetch_basic", lambda _ti: {
        "name": "无行业公司",
        "price": 10,
        "pe_ttm": 20,
        "pb": 2,
        "industry": None,
    })

    result = fetch_peers.main("600519.SH")
    data = result["data"]

    assert result["fallback"] is True
    assert data["peer_table"][0]["is_self"] is True
    assert "industry" in data["fallback_reason"]


def test_valuation_uses_cninfo_market_fallback_when_industry_missing(monkeypatch):
    import fetch_financials
    import fetch_valuation

    monkeypatch.setattr(fetch_valuation.ds, "fetch_basic", lambda _ti: {
        "name": "无行业公司",
        "price": 10,
        "pe_ttm": 20,
        "pb": 2,
        "industry": None,
        "market_cap_raw": 100e8,
    })
    monkeypatch.setattr(fetch_financials, "main", lambda _ticker: {
        "data": {"net_profit_history": [10.0]}
    })
    monkeypatch.setattr(fetch_valuation.ak, "stock_zh_valuation_baidu", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(fetch_valuation.ak, "stock_industry_pe_ratio_cninfo", lambda *a, **kw: pd.DataFrame({
        "行业名称": ["行业A", "行业B"],
        "市盈率-加权": [15.0, 25.0],
    }))

    result = fetch_valuation.main("600519.SH")
    data = result["data"]

    assert data["industry_pe"] == "20.0"
    assert data["industry_pe_fallback_reason"] == "basic.industry 缺失 · 使用 cninfo 市场加权均值"


def test_registry_matches_legacy_output_shapes():
    from lib.pipeline.fetchers.registry import FETCHER_REGISTRY
    from lib.pipeline.schema import DimResult
    from lib.pipeline.validators import validate_result

    cases = {
        "1_financials": {
            "roe": "18.0%",
            "net_margin": "10.0%",
            "revenue_growth": "+5.0%",
            "gross_margin": "30.0%",
            "financial_health": {"debt_ratio": 40, "current_ratio": 2.0, "fcf_margin": 80},
            "ocf": "12.0亿",
            "ocf_history": [12.0, 8.0],
            "ocf_to_net_income_ratio": 1.2,
        },
        "10_valuation": {
            "pe": "20.0",
            "pb": "3.0",
            "pe_quantile": "5 年 60 分位",
            "pb_quantile": "50%",
            "industry_pe": "25.0",
            "dcf": "¥100.0亿",
        },
    }
    for dim_key, data in cases.items():
        spec = FETCHER_REGISTRY[dim_key].spec
        result = validate_result(DimResult(dim_key=dim_key, data=data), spec)
        assert result.data_gaps == []
