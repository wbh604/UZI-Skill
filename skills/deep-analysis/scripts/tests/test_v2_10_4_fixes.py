"""Regression tests for v2.10.4 fixes (Codex-reported bugs).

Bugs:
1. lite mode conflicts with self-review → 9 critical issues because missing dims
2. agent_analysis.json missing always triggers critical even in CLI-only runs
3. ETF early-exit half-broken → `RuntimeError: Stage 2 缺少数据` after 512400 resolve
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ─── Fix 1 & 3: self-review profile-aware ───

def _make_dims(nums):
    return {f"{n}_fake": {"data": {"ok": True}} for n in nums}


def _reset_profile_env():
    for k in ("UZI_DEPTH", "UZI_LITE", "UZI_CLI_ONLY"):
        os.environ.pop(k, None)


def test_check_all_dims_lite_respects_profile():
    """Fix 1 · lite mode must not flag skipped dims as 'completely missing'."""
    _reset_profile_env()
    os.environ["UZI_DEPTH"] = "lite"
    # Force reload profile singleton (analysis_profile caches)
    import importlib
    import lib.analysis_profile as ap
    importlib.reload(ap)
    import lib.self_review as sr
    importlib.reload(sr)

    p = ap.get_profile()
    enabled = {int(k.split("_")[0]) for k in p.fetchers_enabled if k[0].isdigit()}
    ctx = {"dims": _make_dims(enabled), "market": "A", "ag": {}}
    issues = sr.check_all_dims_exist(ctx)
    assert len(issues) == 0, f"lite should not report missing dims; got {[i.issue for i in issues]}"
    _reset_profile_env()


def test_check_empty_dims_lite_respects_profile():
    """Fix 3 · lite mode must not report empty critical on dims it never ran."""
    _reset_profile_env()
    os.environ["UZI_DEPTH"] = "lite"
    import importlib
    import lib.analysis_profile as ap
    importlib.reload(ap)
    import lib.self_review as sr
    importlib.reload(sr)

    p = ap.get_profile()
    enabled = {int(k.split("_")[0]) for k in p.fetchers_enabled if k[0].isdigit()}
    # All enabled dims have good data — no issues expected
    ctx = {"dims": _make_dims(enabled), "market": "A", "ag": {}}
    issues = sr.check_empty_dims(ctx)
    assert len(issues) == 0
    _reset_profile_env()


def test_check_all_dims_medium_still_reports_missing():
    """Medium / default profile must still enforce all 20 dims (regression guard)."""
    _reset_profile_env()
    import importlib
    import lib.analysis_profile as ap
    importlib.reload(ap)
    import lib.self_review as sr
    importlib.reload(sr)

    ctx = {"dims": _make_dims([0, 1, 2]), "market": "A", "ag": {}}
    issues = sr.check_all_dims_exist(ctx)
    assert len(issues) > 10, "medium must still flag missing dims"


# ─── Fix 2: agent_analysis missing warning vs critical ───

def test_agent_analysis_missing_downgrades_in_lite():
    _reset_profile_env()
    os.environ["UZI_DEPTH"] = "lite"
    import importlib
    import lib.self_review as sr
    importlib.reload(sr)

    ctx = {"dims": {}, "market": "A", "ag": None}
    issues = sr.check_agent_analysis_exists(ctx)
    assert len(issues) == 1
    assert issues[0].severity == "warning", (
        f"lite mode should downgrade missing agent_analysis to warning, got {issues[0].severity}"
    )
    _reset_profile_env()


def test_agent_analysis_missing_critical_in_medium():
    _reset_profile_env()
    import importlib
    import lib.self_review as sr
    importlib.reload(sr)

    ctx = {"dims": {}, "market": "A", "ag": None}
    issues = sr.check_agent_analysis_exists(ctx)
    assert len(issues) == 1
    assert issues[0].severity == "critical"


def test_agent_analysis_missing_downgrades_with_cli_only_env():
    _reset_profile_env()
    os.environ["UZI_CLI_ONLY"] = "1"
    import importlib
    import lib.self_review as sr
    importlib.reload(sr)

    ctx = {"dims": {}, "market": "A", "ag": None}
    issues = sr.check_agent_analysis_exists(ctx)
    assert issues[0].severity == "warning"
    _reset_profile_env()


# ─── Fix 4: ETF early-exit from main() ───

def test_main_returns_early_on_non_stock_security(monkeypatch):
    """run_real_test.main() must NOT call stage2 when stage1 returns non_stock_security."""
    import run_real_test as rrt

    etf_result = {
        "status": "non_stock_security",
        "security_type": "etf",
        "ticker": "512400.SH",
        "label": "ETF 基金",
        "top_holdings": [{"rank": 1, "code": "601899.SH", "name": "紫金矿业"}],
    }

    stage2_called = {"flag": False}

    def fake_stage1(_ticker):
        return etf_result

    def fake_stage2(_ticker):
        stage2_called["flag"] = True
        raise RuntimeError("stage2 must not be called for ETF")

    monkeypatch.setattr(rrt, "stage1", fake_stage1)
    monkeypatch.setattr(rrt, "stage2", fake_stage2)

    result = rrt.main("512400.SH")
    assert stage2_called["flag"] is False, "stage2 should NOT be called for non_stock_security"
    assert isinstance(result, dict)
    assert result.get("status") == "non_stock_security"


def test_main_returns_early_on_name_not_resolved(monkeypatch):
    """Existing behavior preserved."""
    import run_real_test as rrt

    err = {"status": "name_not_resolved", "candidates": []}
    stage2_called = {"flag": False}

    monkeypatch.setattr(rrt, "stage1", lambda _t: err)

    def fake_stage2(_t):
        stage2_called["flag"] = True

    monkeypatch.setattr(rrt, "stage2", fake_stage2)

    rrt.main("不存在的股票")
    assert stage2_called["flag"] is False


# ─── v2.10.5 · Codex 反馈 Test 2 新发现：check_coverage_threshold 不 profile-aware ───

def test_coverage_critical_downgrades_in_lite():
    """Fix (v2.10.5) · lite mode should not block HTML on coverage_pct<40 (no agent to fix)."""
    _reset_profile_env()
    os.environ["UZI_DEPTH"] = "lite"
    import importlib
    import lib.analysis_profile as ap
    importlib.reload(ap)
    import lib.self_review as sr
    importlib.reload(sr)

    ctx = {
        "raw": {
            "_integrity": {
                "coverage_pct": 17,
                "missing_critical": [
                    {"dim": "0_basic", "path": "name", "label": "公司名称"}
                ],
            },
            "dimensions": {},
        },
        "dims": {}, "market": "A", "ag": None,
    }
    issues = sr.check_coverage_threshold(ctx)
    assert len(issues) == 1
    assert issues[0].severity == "warning", (
        f"lite mode should downgrade low coverage to warning, got {issues[0].severity}"
    )
    _reset_profile_env()


def test_coverage_critical_preserved_in_medium():
    """Medium/default must still critical on low coverage (regression guard)."""
    _reset_profile_env()
    import importlib
    import lib.analysis_profile as ap
    importlib.reload(ap)
    import lib.self_review as sr
    importlib.reload(sr)

    ctx = {
        "raw": {
            "_integrity": {
                "coverage_pct": 17,
                "missing_critical": [{"dim": "0_basic", "path": "name", "label": "x"}],
            },
            "dimensions": {},
        },
        "dims": {}, "market": "A", "ag": None,
    }
    issues = sr.check_coverage_threshold(ctx)
    assert issues[0].severity == "critical"


def test_raw_market_initialized_from_parse_ticker():
    """Fix (v2.10.6) · raw['market'] must reflect input ticker's market (H/U not defaulted to A).

    Codex review caught this: collect_raw_data hardcoded raw['market']='A', and the
    post-fetch fixup only ran when resolved != input. So passing '00700.HK' directly
    left raw['market']='A'. v2.10.6 pre-populates from parse_ticker.
    """
    import importlib
    import run_real_test as rrt
    importlib.reload(rrt)

    src = Path(rrt.__file__).read_text(encoding="utf-8")
    # Verify pre-fill block exists
    assert "_parse(ticker).market" in src or "parse_ticker as _parse" in src, (
        "collect_raw_data must derive initial market from parse_ticker, not hardcode 'A'"
    )
    # Verify the post-fetch_basic market fixup is unconditional (outside the if resolved_ticker)
    # and reads top-level (not .data.market — fetch_basic puts market at top level)
    assert '_basic_market = dims.get("0_basic", {}).get("market")' in src, (
        "Post fetch_basic must read market from top-level dims['0_basic']['market']"
    )


def test_resume_cache_tries_resolved_ticker():
    """Fix (v2.10.6) · resume must try parse_ticker(ticker).full if raw ticker misses.

    Codex review: user typing '贵州茅台' or '700' misses the cache because lookup
    key is the raw input, not the resolved code. v2.10.6 adds a second lookup
    with the parsed full code.
    """
    import run_real_test as rrt
    src = Path(rrt.__file__).read_text(encoding="utf-8")
    # Must contain dual-lookup logic
    assert "_full = _parse(ticker).full" in src, (
        "resume must fall back to parse_ticker(ticker).full for cache hit"
    )


def test_run_py_sets_cli_only_env():
    """Fix (v2.10.5) · run.py is CLI direct entrypoint · should auto-set UZI_CLI_ONLY=1.

    Agent flow calls stage1/stage2 directly; only humans/CI use run.py. So run.py
    must tell self_review it's CLI-only so agent_analysis.json missing gets warning
    (not critical that blocks HTML).
    """
    run_py = Path(__file__).resolve().parent.parent.parent.parent.parent / "run.py"
    assert run_py.exists()
    src = run_py.read_text(encoding="utf-8")
    assert 'os.environ.setdefault("UZI_CLI_ONLY", "1")' in src, (
        "run.py must set UZI_CLI_ONLY=1 so CLI direct runs produce HTML"
    )


def test_coverage_profile_aware_denominator():
    """Fix (v2.10.5) · denominator should exclude dims not in profile.

    With lite (7 dims: 0_basic, 1_financials, 2_kline, 10_valuation, 11_governance,
    15_events, 16_lhb), CRITICAL_CHECKS items for 7_industry + 14_moat should be
    excluded → fully-populated lite dims should compute ~100% coverage.
    """
    _reset_profile_env()
    os.environ["UZI_DEPTH"] = "lite"
    import importlib
    import lib.analysis_profile as ap
    importlib.reload(ap)
    import lib.self_review as sr
    importlib.reload(sr)

    # Realistic raw: all lite dims have their CRITICAL_CHECKS fields populated
    dims = {
        "0_basic": {"data": {
            "name": "贵州茅台", "price": 1500, "industry": "白酒", "market_cap": 18000,
            "pe_ttm": 25, "pb": 8.5,
        }},
        "1_financials": {"data": {
            "roe_history": [30, 28, 25],
            "revenue_history": [1000, 900, 800],
            "net_profit_history": [500, 400, 350],
            "financial_health": {"ok": True},
        }},
        "2_kline": {"data": {
            "stage": "牛二", "ma_align": "多头", "macd": "金叉",
        }},
        "10_valuation": {"data": {
            "pe": 25, "pe_quantile": 0.6, "pb_quantile": 0.7,
        }},
    }
    ctx = {
        "raw": {
            "_integrity": {"coverage_pct": 80, "missing_critical": []},  # stale
            "dimensions": dims,
        },
        "dims": dims, "market": "A", "ag": None,
    }
    issues = sr.check_coverage_threshold(ctx)
    # With all enabled-dim fields filled, recomputed pct should be high enough
    # that check fires no issue (pct >= 60)
    assert len(issues) == 0, (
        f"lite with full enabled-dim data should produce no coverage issues; got {[i.issue for i in issues]}"
    )
    _reset_profile_env()
