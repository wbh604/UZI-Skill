"""Tests for tier1 · build_earnings_preview（财报前预览 · 多市场）.

最小 mock，断言：
- 返回结构齐全（consensus_table / watch_metrics / scenarios / catalyst_checklist
  / implied_move / methodology_log）
- 三情景 bull/base/bear 齐全且增速单调（bull > base > bear）
- 行业 → 观察指标映射命中（光模块 / 白酒 等本土维度）
- 一致预期缺失时标注「需 web 补充」
- A 股无个股期权 → 用历史财报日波动代替；美股/港股可用期权隐含波动
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from lib.tier1.earnings_preview import build_earnings_preview  # noqa: E402


def _features(**overrides):
    base = {
        "name": "中际旭创", "code": "300308.SZ", "industry": "光模块", "market": "A",
        "price": 120.0, "eps": 4.5, "consensus_eps_2026": 6.2,
        "revenue_latest_yi": 240.0, "revenue_growth_3y_cagr": 45.0,
        "revenue_growth_latest": 60.0, "gross_margin": 33.0,
        "target_price_avg": 150.0, "research_coverage": 28, "buy_rating_pct": 90,
        "volatility_1y": 55.0,
    }
    base.update(overrides)
    return base


# ─── 结构完整性 ──────────────────────────────────────────────────

def test_returns_all_keys():
    out = build_earnings_preview(_features(), {})
    for key in ("consensus_table", "watch_metrics", "scenarios",
                "catalyst_checklist", "implied_move", "methodology_log"):
        assert key in out, f"missing key: {key}"
    assert out["method"] == "Earnings Preview (pre-earnings)"
    assert isinstance(out["methodology_log"], list) and out["methodology_log"]


def test_scenarios_complete():
    out = build_earnings_preview(_features(), {})
    scen = out["scenarios"]
    names = {s["scenario"] for s in scen}
    assert names == {"bull", "base", "bear"}, names
    by = {s["scenario"]: s for s in scen}
    # 每个情景结构齐全
    for s in scen:
        for k in ("revenue_yi", "revenue_growth_pct", "eps",
                  "triggers", "expected_stock_reaction"):
            assert k in s, f"scenario {s['scenario']} missing {k}"
        assert isinstance(s["triggers"], list) and s["triggers"]
    # 增速单调 bull > base > bear
    assert by["bull"]["revenue_growth_pct"] > by["base"]["revenue_growth_pct"]
    assert by["base"]["revenue_growth_pct"] > by["bear"]["revenue_growth_pct"]
    # EPS 弹性：bull > base > bear
    assert by["bull"]["eps"] > by["base"]["eps"] > by["bear"]["eps"]


# ─── 行业 → 观察指标 ────────────────────────────────────────────

def test_sector_metrics_optical():
    out = build_earnings_preview(_features(industry="光模块"), {})
    metrics = " ".join(out["watch_metrics"]["metrics"])
    assert "出货" in metrics or "1.6T" in metrics or "800G" in metrics


def test_sector_metrics_baijiu():
    out = build_earnings_preview(_features(name="贵州茅台", industry="白酒"), {})
    metrics = " ".join(out["watch_metrics"]["metrics"])
    assert "动销" in metrics


def test_sector_metrics_default_fallback():
    out = build_earnings_preview(_features(industry="某冷门行业", name="X"), {})
    assert out["watch_metrics"]["metrics"]  # 非空，落到通用默认


# ─── 一致预期缺失 → 需 web 补充 ──────────────────────────────────

def test_consensus_missing_flagged():
    f = _features(consensus_eps_2026=0, eps=0)
    out = build_earnings_preview(f, {})
    assert out["consensus_notes"], "应有需 web 补充的提示"
    joined = " ".join(r["source"] for r in out["consensus_table"])
    assert "web" in joined


def test_consensus_from_research_dim():
    raw = {"dimensions": {"6_research": {"data": {"consensus_rev_yi": 300.0}}}}
    out = build_earnings_preview(_features(), raw)
    rev_rows = [r for r in out["consensus_table"] if "营收" in r["metric"]]
    assert rev_rows
    assert any(r["consensus"] == 300.0 for r in rev_rows)


# ─── 隐含波动：A 股 vs 美股/港股 ────────────────────────────────

def test_implied_move_a_share_no_options():
    out = build_earnings_preview(_features(market="A"), {})
    im = out["implied_move"]
    assert im["options_available"] is False
    assert "无期权" in im["method"] or "历史" in im["method"]


def test_implied_move_us_options():
    out = build_earnings_preview(_features(market="US"), {})
    im = out["implied_move"]
    assert im["options_available"] is True
    assert "期权" in im["method"] or "straddle" in im["method"].lower()


# ─── 催化剂清单 ──────────────────────────────────────────────────

def test_catalyst_checklist_nonempty():
    out = build_earnings_preview(_features(), {})
    cl = out["catalyst_checklist"]
    assert 3 <= len(cl) <= 5
    for c in cl:
        assert c["item"] and c["why"] and c["importance"] in ("high", "medium", "low")


# ─── 鲁棒性：空输入不崩 ─────────────────────────────────────────

def test_empty_inputs_no_crash():
    out = build_earnings_preview({}, {})
    assert {s["scenario"] for s in out["scenarios"]} == {"bull", "base", "bear"}


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["pytest", "-q", __file__]))
