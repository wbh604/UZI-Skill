"""Tests for lib.tier1.model_update.build_model_update.

覆盖：
- 演示模式（updates=None）：从 features 推断 delta，结构齐全
- 显式模式：用户传新假设 → delta 表正确 + 方向对
- DCF 影响：增长/净利率上修 → 内在价值上升；capex/beta 上升 → 压低
- Comps 影响：净利率上修 → EPS 放大 → 隐含价上升
- thesis 影响 + verdict 综合评级方向
- 缺 dcf_result/comps_result 时优雅降级（available=False）
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def _features():
    return {
        "name": "测试科技", "code": "000001.SZ", "ticker": "000001.SZ",
        "price": 18.5,
        "revenue_growth_latest": 22.0, "revenue_growth_3y_cagr": 15.0,
        "gross_margin": 38.0, "net_margin": 14.0, "pe": 35.0,
        "target_price_avg": 24.0, "eps": 0.62,
    }


def _dcf():
    return {
        "intrinsic_per_share": 20.0,
        "current_price": 18.5,
        "safety_margin_pct": 8.1,
        "assumptions": {"stage1_growth": 0.10, "terminal_g": 0.025, "beta": 1.0},
        "wacc_breakdown": {"wacc": 0.085, "equity_weight": 0.7,
                           "inputs": {"rf": 0.025, "erp": 0.06, "beta": 1.0}},
    }


def _comps():
    return {
        "implied_price": {"via_median_pe": 22.0},
        "target": {"eps": 0.62},
        "peer_stats": {"pe": {"median": 35.5}},
    }


def _build(*args, **kwargs):
    from lib.tier1.model_update import build_model_update
    return build_model_update(*args, **kwargs)


# ─── 演示模式 ──────────────────────────────────────────────────

def test_demo_mode_structure():
    r = _build(_features(), {})
    assert r["mode"] == "demo"
    assert r["method"].startswith("Model Update")
    # delta 表非空且每条字段齐全
    assert len(r["assumption_deltas"]) >= 3
    d0 = r["assumption_deltas"][0]
    for k in ("key", "label", "before", "after", "before_fmt", "after_fmt",
              "delta", "direction", "channel"):
        assert k in d0
    # 影响段 + verdict + log 都在
    assert "dcf_impact" in r and "comps_impact" in r
    assert "thesis_impact" in r and isinstance(r["thesis_impact"], list)
    assert r["verdict"]["rating"]
    assert r["methodology_log"] and len(r["methodology_log"]) >= 4


def test_demo_mode_no_models_graceful():
    r = _build(_features(), {})
    assert r["dcf_impact"]["available"] is False
    assert r["comps_impact"]["available"] is False
    assert "未提供" in r["dcf_impact"]["reason"]


# ─── 显式 delta 表 ─────────────────────────────────────────────

def test_explicit_delta_table():
    r = _build(_features(), {}, updates={"rev_growth": 26.0, "net_margin": 16.0})
    assert r["mode"] == "explicit"
    by_key = {d["key"]: d for d in r["assumption_deltas"]}
    assert "rev_growth" in by_key and "net_margin" in by_key
    rg = by_key["rev_growth"]
    # before 取基准源 revenue_growth_3y_cagr=15.0，after=用户新假设 26 → ↑
    assert rg["after"] == 26.0
    assert rg["before"] == 15.0
    assert rg["direction"] == "↑"
    assert rg["delta"] == 11.0


# ─── DCF 传导 ──────────────────────────────────────────────────

def test_dcf_impact_upside_on_growth():
    r = _build(_features(), {}, updates={"rev_growth": 30.0, "net_margin": 18.0},
               dcf_result=_dcf())
    di = r["dcf_impact"]
    assert di["available"] is True
    assert di["intrinsic_before"] == 20.0
    # 增速 + 净利率双升 → 内在价值上升
    assert di["intrinsic_after"] > di["intrinsic_before"]
    assert di["delta_pct"] > 0
    assert di["direction"] == "↑"
    assert di["drivers"]


def test_dcf_impact_downside_on_capex_and_beta():
    r = _build(_features(), {}, updates={"capex_pct": 12.0, "beta": 1.5},
               dcf_result=_dcf())
    di = r["dcf_impact"]
    assert di["available"] is True
    # capex 上升压 FCF + beta 上升抬 WACC → 内在价值下降
    assert di["intrinsic_after"] < di["intrinsic_before"]
    assert di["wacc_after_pct"] > di["wacc_before_pct"]


# ─── Comps 传导 ────────────────────────────────────────────────

def test_comps_impact_on_margin():
    r = _build(_features(), {}, updates={"net_margin": 16.0},
               comps_result=_comps())
    ci = r["comps_impact"]
    assert ci["available"] is True
    # 净利率 14→16 放大 EPS → 隐含价上升
    assert ci["implied_pe_after"] > ci["implied_pe_before"]
    assert ci["direction"] == "↑"


def test_comps_missing_graceful():
    r = _build(_features(), {}, updates={"net_margin": 16.0})
    assert r["comps_impact"]["available"] is False


# ─── thesis + verdict ─────────────────────────────────────────

def test_thesis_and_verdict_bullish():
    r = _build(_features(), {},
               updates={"rev_growth": 30.0, "net_margin": 18.0, "gross_margin": 42.0},
               dcf_result=_dcf(), comps_result=_comps())
    # 全是利多改动 → 至少有强化支柱 + 评级上修
    strengthened = [t for t in r["thesis_impact"] if t["impact"].startswith("💪")]
    assert len(strengthened) >= 2
    assert r["verdict"]["composite_score"] > 0
    assert "上修" in r["verdict"]["rating"] or "Upgrade" in r["verdict"]["rating"]


def test_verdict_bearish_on_negative_updates():
    r = _build(_features(), {},
               updates={"rev_growth": 8.0, "net_margin": 9.0, "capex_pct": 14.0},
               dcf_result=_dcf(), comps_result=_comps())
    assert r["verdict"]["composite_score"] < 0
    assert "下修" in r["verdict"]["rating"] or "Downgrade" in r["verdict"]["rating"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
