"""Missing moat evidence must neither crash nor produce invented ratings."""
import pytest

from lib.deep_analysis_methods import build_competitive_analysis
from lib.report.institutional import _render_competitive_analysis


@pytest.mark.parametrize("scores", [None, [], "invalid", {},
    {"intangible": "NaN", "switching": 7, "scale": 6},
    {"intangible": 7, "switching": None, "scale": 6},
    {"intangible": 70, "switching": 7, "scale": 6}])
def test_missing_scores_do_not_invent_porter_ratings(scores):
    result = build_competitive_analysis({}, {"dimensions": {"14_moat": {"data": {"scores": scores}}}})
    assert result["porter_five_forces"] == {}
    assert result["industry_attractiveness_pct"] is None
    assert result["bcg_position"]["category"] == "未评估"
    assert result["data_quality"] == "unavailable"
    html = _render_competitive_analysis({"competitive_analysis": result})
    assert "未评估" in html
    assert "<svg" not in html
    assert "None" not in html


def test_unavailable_flag_overrides_scores_but_keeps_valid_bcg():
    result = build_competitive_analysis({"market_share": 5, "industry_growth": 20}, {
        "dimensions": {"14_moat": {"data": {
            "scores": {"intangible": 8, "switching": 8, "scale": 8},
            "scores_available": False,
        }}}})
    assert result["porter_five_forces"] == {}
    assert result["bcg_position"]["category"] == "Star (明星)"
    assert result["data_quality"] == "partial"


def test_valid_moat_scores_still_render():
    result = build_competitive_analysis({"market_share": 5, "industry_growth": 20}, {
        "dimensions": {"14_moat": {"data": {
            "scores": {"intangible": 8, "switching": 6, "scale": 8},
        }}}})
    assert result["porter_five_forces"]["new_entrants_threat"]["score"] == 2
    assert result["data_quality"] == "available"
    assert "<svg" in _render_competitive_analysis({"competitive_analysis": result})


def test_partial_moat_evidence_does_not_use_placeholder_scores():
    result = build_competitive_analysis({}, {"dimensions": {"14_moat": {"data": {
        "scores": {"intangible": 8, "switching": 5, "scale": 5},
        "scores_available": True,
        "scores_evidence": {"intangible": True, "switching": False, "scale": False},
    }}}})
    assert result["porter_five_forces"] == {}
    assert result["industry_attractiveness_pct"] is None


def test_zero_moat_scores_remain_valid_and_within_five_point_scale():
    result = build_competitive_analysis({}, {"dimensions": {"14_moat": {"data": {
        "scores": {"intangible": 0, "switching": 0, "scale": 0},
    }}}})
    assert result["porter_five_forces"]["new_entrants_threat"]["score"] == 5
    assert all(1 <= force["score"] <= 5 for force in result["porter_five_forces"].values())
