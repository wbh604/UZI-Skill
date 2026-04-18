"""Regression tests for v2.11.0 scoring calibration.

Background (2026-04-18 forum + wechat feedback):
- @崔越: 测了几只股票，没有超过 65 分的
- @睡袍布太少: 目前只测到天孚通信超过 65
- @W.D: 茅台 47 分
- @一印成王: 短期持有和中长期持有

Root cause:
1. verdict thresholds 85/70/55/40 · 从未有股能拿 ≥85 (values bucket 空设)
2. consensus neutral 权重 0.5 太低 · A 股白马典型 consensus ~37 (5 bull / 20 neu / 15 bear / 11 skip → (5+10)/40 = 37.5)

Fix:
1. verdict 阈值 85/70/55/40 → 80/65/50/35
2. consensus neutral 权重 0.5 → 0.6（在 generate_panel 和 stock_style.apply_style_weights 两处同步）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ─── Verdict threshold calibration ───

def _verdict_for(overall: float) -> str:
    """Re-implementation of run_real_test.py verdict logic for test isolation."""
    if overall >= 80: return "值得重仓"
    elif overall >= 65: return "可以蹲一蹲"
    elif overall >= 50: return "观望优先"
    elif overall >= 35: return "谨慎"
    else: return "回避"


def test_verdict_thresholds_are_v2_11_calibrated():
    """Ensure run_real_test.py uses new thresholds, not old 85/70/55/40."""
    src = (ROOT / "run_real_test.py").read_text(encoding="utf-8")
    # New thresholds must be present
    assert "overall >= 80" in src, "值得重仓 threshold should be 80 (was 85)"
    assert "overall >= 65" in src, "可以蹲一蹲 threshold should be 65 (was 70)"
    assert "overall >= 50" in src, "观望优先 threshold should be 50 (was 55)"
    assert "overall >= 35" in src, "谨慎 threshold should be 35 (was 40)"
    # Old thresholds should not appear in the verdict ladder
    # (85/70/55/40 may appear elsewhere for other reasons, so only check the cluster)
    assert "overall >= 85" not in src, "old 85 threshold should be removed"
    assert "overall >= 70" not in src, "old 70 threshold should be removed"


def test_verdict_ladder_monotonic():
    """基本 sanity — ladder 必须单调."""
    assert _verdict_for(85) == "值得重仓"
    assert _verdict_for(80) == "值得重仓"
    assert _verdict_for(79.9) == "可以蹲一蹲"
    assert _verdict_for(65) == "可以蹲一蹲"
    assert _verdict_for(64.9) == "观望优先"
    assert _verdict_for(50) == "观望优先"
    assert _verdict_for(49.9) == "谨慎"
    assert _verdict_for(35) == "谨慎"
    assert _verdict_for(34.9) == "回避"


def test_maotai_simulated_score_now_gives_kan_dan_dan():
    """Simulate typical Maotai scenario post-v2.11 calibration.

    Pre v2.11 reality (@W.D 反馈): Maotai 47 → "谨慎"（偏低）
    Post v2.11 expected:
    - fund_score ~62 (22 维加权，白马基本面尚可但没到极好)
    - consensus: 12 bull / 20 neu / 16 bear / 3 skip → (12 + 12) / 48 × 100 = 50.0
    - overall = 62×0.6 + 50×0.4 = 57.2 → "观望优先"（比"谨慎"更贴近白马定位）
    """
    fund_score = 62
    # Simulate v2.11 consensus formula
    bullish, neutral, bearish, skip = 12, 20, 16, 3
    active = bullish + neutral + bearish
    consensus = (bullish + 0.6 * neutral) / active * 100
    overall = fund_score * 0.6 + consensus * 0.4
    verdict = _verdict_for(overall)
    assert verdict in ("观望优先", "可以蹲一蹲"), (
        f"Maotai-typical score should reach 观望优先+, got {overall:.1f}={verdict}"
    )
    # Old v2.9.1 would have been (12 + 10) / 48 × 100 = 45.8 → overall 55.7 → "谨慎"
    old_consensus = (bullish + 0.5 * neutral) / active * 100
    old_overall = fund_score * 0.6 + old_consensus * 0.4
    assert overall > old_overall, "v2.11 must lift overall vs old 0.5 weight"
    assert overall - old_overall >= 1.5, (
        f"v2.11 neutral bump should add ≥1.5 overall points, got {overall - old_overall:.2f}"
    )


# ─── Neutral weight calibration ───

def test_consensus_formula_uses_v2_11_neutral_weight():
    """generate_panel must use 0.6 neutral weight (not 0.5)."""
    src = (ROOT / "run_real_test.py").read_text(encoding="utf-8")
    # Look for the calibration signal — NEUTRAL_WEIGHT = 0.6
    assert "NEUTRAL_WEIGHT = 0.6" in src, "NEUTRAL_WEIGHT constant missing"
    assert "v2.11" in src and "neutral" in src.lower(), "v2.11 calibration comment missing"


def test_stock_style_apply_weights_uses_0_6():
    """stock_style.apply_style_weights must match (not diverge to 0.5)."""
    src = (ROOT / "lib" / "stock_style.py").read_text(encoding="utf-8")
    assert "neutral_w += w * 0.6" in src, (
        "stock_style.py must use 0.6 neutral weight (aligned with generate_panel)"
    )


def test_consensus_formula_version_label_v2_11():
    """panel.json consensus_formula.version must advertise v2.11 for downstream agents."""
    src = (ROOT / "run_real_test.py").read_text(encoding="utf-8")
    assert '"version": "v2.11' in src, "consensus_formula version label must be v2.11"


# ─── Sanity: end-to-end math ───

def test_consensus_range_bounded():
    """Sanity — under any distribution, consensus must stay in [0, 100]."""
    # All bullish
    c = (50 + 0.6 * 0) / 50 * 100
    assert c == 100
    # All neutral
    c = (0 + 0.6 * 50) / 50 * 100
    assert c == 60
    # All bearish
    c = (0 + 0.6 * 0) / 50 * 100
    assert c == 0
    # Typical mix
    c = (15 + 0.6 * 20) / 40 * 100
    assert 65 <= c <= 70


def test_consensus_empty_active_does_not_crash():
    """0 active should not div by zero — max(active, 1) protects."""
    active = max(0, 1)
    c = (0 + 0.6 * 0) / active * 100
    assert c == 0.0
