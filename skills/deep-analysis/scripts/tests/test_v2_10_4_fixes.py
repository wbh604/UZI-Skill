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
