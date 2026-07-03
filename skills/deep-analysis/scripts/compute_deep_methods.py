"""Dimensions 20-22 — machine-computed institutional analysis.

Runs AFTER Task 1 (raw data collection). These are pure-compute dims that
don't need network calls — they consume raw_data + features and return
structured analysis dicts.

Usage (from run_real_test after collect_raw_data + feature extraction):

    from compute_deep_methods import compute_dim_20, compute_dim_21, compute_dim_22
    raw["dimensions"]["20_valuation_models"] = compute_dim_20(features, raw)
    raw["dimensions"]["21_research_workflow"] = compute_dim_21(features, raw)
    raw["dimensions"]["22_deep_methods"] = compute_dim_22(features, raw, dim_20, dim_21)
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib.fin_models import (
    compute_dcf, build_comps_table, project_three_stmt, quick_lbo, accretion_dilution
)
from lib.research_workflow import (
    build_initiating_coverage, build_earnings_analysis, build_catalyst_calendar,
    build_thesis_tracker, build_morning_note, run_idea_screen, build_sector_overview,
)
from lib.deep_analysis_methods import (
    build_ic_memo, build_unit_economics, build_value_creation_plan,
    build_dd_checklist, build_competitive_analysis, build_portfolio_rebalance,
)


# ═══════════════════════════════════════════════════════════════
# DIM 20 · VALUATION MODELS
# ═══════════════════════════════════════════════════════════════

def compute_dim_20(features: dict, raw: dict) -> dict:
    """DCF + Comps + 3-stmt + LBO packaged as dim 20."""
    dcf = compute_dcf(features)
    three_stmt = project_three_stmt(features)
    lbo = quick_lbo(features)

    # Comps needs peer data
    dims = raw.get("dimensions", {}) or {}
    # ─── Peer data adapter: merge 4_peers.peer_table AND top-level similar_stocks ───
    peers_dim = (dims.get("4_peers") or {}).get("data") or {}
    peer_table = peers_dim.get("peer_table") or peers_dim.get("peer_comparison") or []
    similar_stocks = raw.get("similar_stocks") or []

    target_for_comps = {
        "name": features.get("name", "目标公司"),
        "pe": features.get("pe"),
        "pb": features.get("pb"),
        "ps": features.get("ps"),
        "roe": features.get("roe_last"),
        "net_margin": features.get("net_margin"),
        "revenue_growth": features.get("rev_growth_3y"),
        "market_cap_yi": features.get("market_cap_yi"),
        "price": features.get("price"),
        "eps": features.get("eps"),
        "bvps": features.get("bvps"),
    }

    def _normalize_peer(p: dict) -> dict:
        """Translate heterogeneous peer record → comps schema."""
        if not isinstance(p, dict):
            return {}
        # market_cap handling: can be "860.7亿" string or number
        mc_raw = p.get("market_cap") or p.get("market_cap_yi") or 0
        try:
            mc = float(str(mc_raw).replace("亿", "").replace(",", "").strip()) if mc_raw else 0
        except (ValueError, TypeError):
            mc = 0
        px = 0
        try:
            px = float(p.get("price") or 0)
        except (ValueError, TypeError):
            px = 0
        return {
            "name": p.get("name") or p.get("ticker") or p.get("code", ""),
            "ticker": p.get("ticker") or p.get("code", ""),
            "pe": p.get("pe") or p.get("pe_ttm"),
            "pb": p.get("pb"),
            "ps": p.get("ps"),
            "ev_ebitda": p.get("ev_ebitda"),
            "ev_sales": p.get("ev_sales"),
            "roe": p.get("roe"),
            "net_margin": p.get("net_margin"),
            "revenue_growth": p.get("revenue_growth") or p.get("rev_growth"),
            "market_cap_yi": mc,
            "price": px,
        }

    peer_list_for_comps = []
    seen = set()
    # Priority 1: peer_table (higher detail if available)
    if isinstance(peer_table, list):
        for p in peer_table[:10]:
            np = _normalize_peer(p)
            if np and np.get("name") and np.get("name") not in seen:
                peer_list_for_comps.append(np)
                seen.add(np["name"])
    # Priority 2: similar_stocks (wave 3 — almost always has data)
    if isinstance(similar_stocks, list):
        for p in similar_stocks[:10]:
            np = _normalize_peer(p)
            if np and np.get("name") and np.get("name") not in seen:
                peer_list_for_comps.append(np)
                seen.add(np["name"])

    comps = build_comps_table(target_for_comps, peer_list_for_comps)

    return {
        "data": {
            "dcf": dcf,
            "comps": comps,
            "three_statement": three_stmt,
            "lbo": lbo,
            "summary": {
                "dcf_intrinsic": dcf.get("intrinsic_per_share"),
                "dcf_safety_margin_pct": dcf.get("safety_margin_pct"),
                "dcf_verdict": dcf.get("verdict"),
                "lbo_irr_pct": lbo.get("irr_pct"),
                "lbo_verdict": lbo.get("verdict"),
                "comps_verdict": comps.get("valuation_verdict") if "valuation_verdict" in comps else "—",
            },
        },
        "source": "compute:fin_models (DCF/Comps/3-stmt/LBO)",
        "fallback": False,
    }


# ═══════════════════════════════════════════════════════════════
# DIM 21 · RESEARCH WORKFLOW
# ═══════════════════════════════════════════════════════════════

def compute_dim_21(features: dict, raw: dict, dim_20_data: dict | None = None) -> dict:
    """Initiating + Earnings + Catalyst + Thesis + Morning + Screen + Sector."""
    dcf_r = (dim_20_data or {}).get("dcf") if dim_20_data else None
    comps_r = (dim_20_data or {}).get("comps") if dim_20_data else None

    initiating = build_initiating_coverage(features, raw, dcf_r, comps_r)
    earnings = build_earnings_analysis(features, raw)
    catalysts = build_catalyst_calendar(features, raw)
    thesis = build_thesis_tracker(features, raw)
    morning = build_morning_note(features, raw)
    screens = {
        "value": run_idea_screen(features, "value"),
        "growth": run_idea_screen(features, "growth"),
        "quality": run_idea_screen(features, "quality"),
        "gulp": run_idea_screen(features, "gulp"),
    }
    sector = build_sector_overview(features, raw)

    return {
        "data": {
            "initiating_coverage": initiating,
            "earnings_analysis": earnings,
            "catalyst_calendar": catalysts,
            "thesis_tracker": thesis,
            "morning_note": morning,
            "idea_screens": screens,
            "sector_overview": sector,
            "summary": {
                "rec_rating": initiating.get("headline", {}).get("rating"),
                "target_price": initiating.get("headline", {}).get("target_price"),
                "upside_pct": initiating.get("headline", {}).get("upside_pct"),
                "thesis_intact_pct": thesis.get("thesis_intact_pct"),
                "next_high_impact_event": catalysts.get("next_30d", [{}])[0].get("event") if catalysts.get("next_30d") else "—",
                "earnings_headline": earnings.get("headline"),
                "screens_passed": sum(1 for s in screens.values() if s.get("fits_screen")),
            },
        },
        "source": "compute:research_workflow (7 research products)",
        "fallback": False,
    }


# ═══════════════════════════════════════════════════════════════
# DIM 22 · DEEP ANALYSIS METHODS
# ═══════════════════════════════════════════════════════════════

def compute_dim_22(features: dict, raw: dict, dim_20_data: dict | None = None, dim_21_data: dict | None = None) -> dict:
    """IC Memo + Unit Econ + VCP + DD + Porter/BCG + Rebalance."""
    dcf_r = (dim_20_data or {}).get("dcf") if dim_20_data else None
    comps_r = (dim_20_data or {}).get("comps") if dim_20_data else None

    ic_memo = build_ic_memo(features, raw, dcf_r, comps_r)
    unit_econ = build_unit_economics(features, raw)
    vcp = build_value_creation_plan(features, raw)
    dd = build_dd_checklist(features, raw)
    competitive = build_competitive_analysis(features, raw)
    # Rebalance is optional — only runs if the user has positions. Here we
    # generate a sample single-position "what if you hold this stock" view.
    sample_positions = [{
        "ticker": features.get("ticker", "—"),
        "name": features.get("name", "—"),
        "market_value_yuan": 10000,
        "asset_class": "A股成长",
        "cost_basis": 9500,
    }]
    rebalance = build_portfolio_rebalance(sample_positions)

    return {
        "data": {
            "ic_memo": ic_memo,
            "unit_economics": unit_econ,
            "value_creation_plan": vcp,
            "dd_checklist": dd,
            "competitive_analysis": competitive,
            "portfolio_rebalance": rebalance,
            "summary": {
                "ic_recommendation": ic_memo.get("sections", {}).get("I_exec_summary", {}).get("headline"),
                "bcg_position": competitive.get("bcg_position", {}).get("category"),
                "industry_attractiveness": competitive.get("industry_attractiveness_pct"),
                "dd_completion_pct": dd.get("completion_pct"),
                "value_creation_uplift_yi": vcp.get("total_uplift_yi"),
                "unit_economics_verdict": unit_econ.get("verdict") if "verdict" in unit_econ else "—",
            },
        },
        "source": "compute:deep_analysis_methods (6 PE/IB/WM methods)",
        "fallback": False,
    }


if __name__ == "__main__":
    import json
    raw = {"dimensions": {}, "ticker": "TEST"}
    features = {
        "price": 18.5, "market_cap_yi": 260, "shares_outstanding_yi": 14.0,
        "revenue_latest_yi": 52, "net_margin": 12.5, "pe": 35, "pb": 2.8,
        "total_debt_yi": 10, "cash_yi": 40, "fcf_latest_yi": 6.5,
        "ebitda_yi": 10, "equity_yi": 92, "name": "测试公司",
        "roe_last": 11.8, "roe_5y_above_15": 0, "ocf_positive": True,
        "moat_total": 27, "stage_num": 2, "rev_growth_3y": 18,
        "eps_growth_3y": 15, "debt_ratio": 30, "gross_margin": 35,
    }
    d20 = compute_dim_20(features, raw)
    print("DIM 20 summary:", json.dumps(d20["data"]["summary"], ensure_ascii=False, indent=2))
    d21 = compute_dim_21(features, raw, d20["data"])
    print("\nDIM 21 summary:", json.dumps(d21["data"]["summary"], ensure_ascii=False, indent=2))
    d22 = compute_dim_22(features, raw, d20["data"], d21["data"])
    print("\nDIM 22 summary:", json.dumps(d22["data"]["summary"], ensure_ascii=False, indent=2))
