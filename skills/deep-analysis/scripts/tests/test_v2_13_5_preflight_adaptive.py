"""Regression tests for v2.13.5 · NetworkProfile + 自适应 DIM_STRATEGIES + agent HARD-GATE.

三层验证：
1. NetworkProfile 9 目标 3 组 + 代理检测 + 缓存
2. DIM_STRATEGIES 按 network 自适应过滤
3. SKILL.md + AGENTS.md 含 HARD-GATE-PLAYWRIGHT-AUTOFILL
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def _reset_env():
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy",
              "https_proxy", "all_proxy", "UZI_PLAYWRIGHT_ENABLE",
              "UZI_PLAYWRIGHT_FORCE", "UZI_DEPTH"):
        os.environ.pop(k, None)


# ─── Layer 1 · NetworkProfile ─────────────────────────────────────

def test_network_profile_dataclass_exists():
    from lib.network_preflight import NetworkProfile
    assert hasattr(NetworkProfile, "domestic_ok")
    assert hasattr(NetworkProfile, "overseas_ok")
    assert hasattr(NetworkProfile, "search_ok")
    assert hasattr(NetworkProfile, "has_proxy")
    assert hasattr(NetworkProfile, "recommendation")


def test_detect_proxy_from_env():
    from lib.network_preflight import _detect_proxy
    _reset_env()
    has, url = _detect_proxy()
    assert has is False
    assert url == ""

    os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7890"
    has, url = _detect_proxy()
    assert has is True
    assert "7890" in url
    _reset_env()


def test_detect_proxy_ignores_lowercase_off():
    from lib.network_preflight import _detect_proxy
    _reset_env()
    os.environ["http_proxy"] = "off"
    has, _ = _detect_proxy()
    assert has is False
    _reset_env()


def test_run_preflight_writes_cache_json():
    from lib.network_preflight import run_preflight
    _reset_env()
    # mock _probe so network tests don't hit real net
    from lib import network_preflight as np

    def fake_probe(domain, port=443, timeout=3.0):
        return np.DomainCheck(domain=domain, group="", reachable=True, latency_ms=5)

    with patch.object(np, "_probe", side_effect=fake_probe):
        prof = run_preflight(verbose=False)

    assert prof.domestic_ok
    assert prof.overseas_ok
    assert prof.search_ok
    cache = SCRIPTS / ".cache" / "_global" / "network_profile.json"
    assert cache.exists()
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert data["severity"] in ("ok", "warning", "degraded", "critical")
    assert "recommendation" in data


def test_recommendation_varies_by_profile():
    from lib.network_preflight import NetworkProfile, _build_recommendation
    # 国内通 + 境外受限 · 典型大陆无代理
    p = NetworkProfile(
        domestic_ok=True, overseas_ok=False, search_ok=True,
        domestic_count=3, overseas_count=0, search_count=2,
    )
    rec, sev = _build_recommendation(p)
    assert "国内" in rec and "境外" in rec
    assert "Playwright" in rec

    # 全通
    p2 = NetworkProfile(domestic_ok=True, overseas_ok=True, search_ok=True,
                        domestic_count=3, overseas_count=3, search_count=3)
    rec2, sev2 = _build_recommendation(p2)
    assert sev2 == "ok"

    # 全不通
    p3 = NetworkProfile(domestic_ok=False, overseas_ok=False, search_ok=False,
                        domestic_count=0, overseas_count=0, search_count=0)
    rec3, sev3 = _build_recommendation(p3)
    assert sev3 == "critical"


def test_get_network_profile_uses_cache():
    from lib import network_preflight as np
    # 手写一个 fresh profile 到 cache
    cache = SCRIPTS / ".cache" / "_global" / "network_profile.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    fresh_data = {
        "domestic_ok": True, "overseas_ok": False, "search_ok": True,
        "has_proxy": False, "proxy_url": "",
        "domestic_count": 3, "overseas_count": 0, "search_count": 2,
        "avg_latency_ms": 10,
        "probed_at": time.time(),  # fresh
        "severity": "warning", "recommendation": "stale test",
    }
    cache.write_text(json.dumps(fresh_data), encoding="utf-8")

    # Mock _probe so we can detect if run_preflight re-runs
    probe_called = {"flag": False}
    def fake_probe(*a, **k):
        probe_called["flag"] = True
        return np.DomainCheck(domain="x", group="", reachable=True, latency_ms=1)

    with patch.object(np, "_probe", side_effect=fake_probe):
        prof = np.get_network_profile(max_age_sec=3600)

    assert prof.recommendation == "stale test"  # 从 cache 读
    assert probe_called["flag"] is False  # 没触发 re-probe


def test_get_network_profile_reprobes_when_stale():
    from lib import network_preflight as np
    cache = SCRIPTS / ".cache" / "_global" / "network_profile.json"
    stale_data = {
        "domestic_ok": False, "probed_at": time.time() - 99999,  # 过期
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(stale_data), encoding="utf-8")

    probe_called = {"count": 0}
    def fake_probe(*a, **k):
        probe_called["count"] += 1
        return np.DomainCheck(domain="x", group="", reachable=True, latency_ms=1)

    with patch.object(np, "_probe", side_effect=fake_probe):
        np.get_network_profile(max_age_sec=60)

    assert probe_called["count"] > 0  # 触发了 re-probe


# ─── Layer 3 · DIM_STRATEGIES 自适应 ──────────────────────────────

def test_dim_network_requirements_complete():
    """10 个维度都应在 DIM_NETWORK_REQUIREMENTS 里."""
    from lib.playwright_fallback import DIM_STRATEGIES, DIM_NETWORK_REQUIREMENTS
    for dim in DIM_STRATEGIES.keys():
        assert dim in DIM_NETWORK_REQUIREMENTS, f"{dim} 缺网络需求声明"


def test_filter_dims_by_network_drops_domestic_when_offline():
    from lib import playwright_fallback as pf
    from lib.network_preflight import NetworkProfile

    fake_profile = NetworkProfile(
        domestic_ok=False, overseas_ok=True, search_ok=True,
        domestic_count=0, overseas_count=3, search_count=3,
    )
    with patch("lib.network_preflight.get_network_profile", return_value=fake_profile):
        dims = frozenset({"4_peers", "7_industry", "8_materials"})
        eff, skipped = pf._filter_dims_by_network(dims)
    assert len(eff) == 0, "域不通时所有 domestic 维度都应跳"
    assert len(skipped) == 3


def test_filter_dims_by_network_drops_search_when_search_offline():
    from lib import playwright_fallback as pf
    from lib.network_preflight import NetworkProfile

    fake_profile = NetworkProfile(
        domestic_ok=True, overseas_ok=False, search_ok=False,
        domestic_count=3, overseas_count=0, search_count=0,
    )
    with patch("lib.network_preflight.get_network_profile", return_value=fake_profile):
        dims = frozenset({"4_peers", "7_industry", "18_trap"})
        eff, skipped = pf._filter_dims_by_network(dims)
    # 4_peers 仅需 domestic · 保留
    assert "4_peers" in eff
    # 7_industry / 18_trap 需 search · 跳
    assert "7_industry" not in eff
    assert "18_trap" not in eff


def test_filter_dims_keeps_all_when_network_ok():
    from lib import playwright_fallback as pf
    from lib.network_preflight import NetworkProfile

    fake_profile = NetworkProfile(
        domestic_ok=True, overseas_ok=True, search_ok=True,
        domestic_count=3, overseas_count=3, search_count=3,
    )
    with patch("lib.network_preflight.get_network_profile", return_value=fake_profile):
        dims = frozenset({"4_peers", "7_industry", "18_trap", "14_moat"})
        eff, skipped = pf._filter_dims_by_network(dims)
    assert eff == dims
    assert skipped == []


# ─── Layer 2 · HARD-GATE 文档检查 ────────────────────────────────

def test_skill_md_has_playwright_autofill_gate():
    skill = Path(SCRIPTS).parent / "SKILL.md"
    txt = skill.read_text(encoding="utf-8")
    assert "HARD-GATE-PLAYWRIGHT-AUTOFILL" in txt
    assert "autofill_via_playwright" in txt
    assert "UZI_PLAYWRIGHT_FORCE" in txt
    assert "network_profile.json" in txt


def test_agents_md_has_playwright_prefetch_step():
    agents = Path(SCRIPTS).parent.parent.parent / "AGENTS.md"
    txt = agents.read_text(encoding="utf-8")
    assert "Playwright 兜底前置" in txt or "autofill_via_playwright" in txt
    assert "_review_issues.json" in txt


def test_analyze_stock_command_has_prefetch():
    cmd = Path(SCRIPTS).parent.parent.parent / "commands" / "analyze-stock.md"
    txt = cmd.read_text(encoding="utf-8")
    assert "autofill_via_playwright" in txt
    assert "UZI_PLAYWRIGHT_FORCE" in txt
