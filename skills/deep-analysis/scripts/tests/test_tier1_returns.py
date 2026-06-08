"""Tests for tier1 · 二级市场组合收益归因 (returns_attrib).

核心命题：组合总收益 = Σ(权重 × 个股收益)，且行业/流派分组贡献加总必须等于总收益。
覆盖：
- 贡献加总 ≈ 总收益（最小 mock holdings）
- 行业归因分组加总 == 总收益
- Top 贡献 / Top 拖累 排序正确
- 权重归一化（含 0-100 形式 + 缺失等权）
- 缺 return_pct → needs_price 标注、按 0 计、计入 missing
- benchmark 超额计算
- 空 holdings 容错

注：tier1/ 无 __init__.py（按要求不建），故用 importlib 按文件路径加载，
sys.path 仍指向 scripts 根（参考 tests/test_serenity_rules.py）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

_MOD_PATH = SCRIPTS / "lib" / "tier1" / "returns_attrib.py"
_spec = importlib.util.spec_from_file_location("returns_attrib", _MOD_PATH)
returns_attrib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(returns_attrib)
build_returns_attribution = returns_attrib.build_returns_attribution


def _holdings():
    """最小 mock · 权重和 = 1.0 · 全带 return_pct。"""
    return [
        {"ticker": "600519.SH", "weight": 0.40, "return_pct": 10.0, "industry": "白酒", "name": "茅台"},
        {"ticker": "000858.SZ", "weight": 0.30, "return_pct": -5.0, "industry": "白酒", "name": "五粮液"},
        {"ticker": "002594.SZ", "weight": 0.30, "return_pct": 20.0, "industry": "电动车", "name": "比亚迪"},
    ]


# ─── 核心：贡献加总 ≈ 总收益 ──────────────────────────────────────

def test_contribution_sums_to_total():
    r = build_returns_attribution(_holdings())
    # 0.4*10 + 0.3*(-5) + 0.3*20 = 4 - 1.5 + 6 = 8.5
    assert abs(r["total_return"] - 8.5) < 1e-6
    summed = sum(c["contribution_pct"] for c in r["contribution_table"])
    assert abs(summed - r["total_return"]) < 1e-6


def test_sector_attribution_sums_to_total():
    r = build_returns_attribution(_holdings())
    sec_sum = sum(s["contribution_pct"] for s in r["sector_attribution"])
    assert abs(sec_sum - r["total_return"]) < 1e-6
    # 白酒 = 0.4*10 + 0.3*(-5) = 2.5；电动车 = 6.0
    by_ind = {s["industry"]: s["contribution_pct"] for s in r["sector_attribution"]}
    assert abs(by_ind["白酒"] - 2.5) < 1e-6
    assert abs(by_ind["电动车"] - 6.0) < 1e-6


# ─── 结构完整性 ──────────────────────────────────────────────────

def test_structure_keys():
    r = build_returns_attribution(_holdings(), benchmark_return=5.0)
    for k in ("total_return", "contribution_table", "sector_attribution",
              "top_contributors", "top_detractors", "benchmark", "methodology_log",
              "verdict"):
        assert k in r, f"缺字段 {k}"
    assert isinstance(r["methodology_log"], list) and r["methodology_log"]
    assert isinstance(r["contribution_table"], list)


# ─── Top 贡献 / 拖累排序 ──────────────────────────────────────────

def test_top_contributors_and_detractors():
    r = build_returns_attribution(_holdings())
    assert r["top_contributors"][0]["ticker"] == "002594.SZ"  # +6.0pp
    assert r["top_detractors"][0]["ticker"] == "000858.SZ"    # -1.5pp
    # 贡献全部 > 0，拖累全部 < 0
    assert all(c["contribution_pct"] > 0 for c in r["top_contributors"])
    assert all(c["contribution_pct"] < 0 for c in r["top_detractors"])


# ─── 权重归一化 ──────────────────────────────────────────────────

def test_weight_normalization_pct_form():
    # 用 0-100 形式 + 不归一（和=120）→ 自动 /100 再归一
    h = [
        {"ticker": "A", "weight": 60, "return_pct": 10.0, "industry": "X"},
        {"ticker": "B", "weight": 60, "return_pct": 10.0, "industry": "X"},
    ]
    r = build_returns_attribution(h)
    ws = [c["weight"] for c in r["contribution_table"]]
    assert abs(sum(ws) - 1.0) < 1e-6
    assert abs(ws[0] - 0.5) < 1e-6
    assert abs(r["total_return"] - 10.0) < 1e-6  # 两只都 +10%


def test_missing_weights_equal_weight():
    h = [
        {"ticker": "A", "return_pct": 10.0, "industry": "X"},
        {"ticker": "B", "return_pct": 30.0, "industry": "X"},
    ]
    r = build_returns_attribution(h)
    ws = [c["weight"] for c in r["contribution_table"]]
    assert all(abs(w - 0.5) < 1e-6 for w in ws)
    assert abs(r["total_return"] - 20.0) < 1e-6


# ─── 缺 return_pct → 标注需补价格 ────────────────────────────────

def test_missing_return_flagged():
    h = [
        {"ticker": "A", "weight": 0.5, "return_pct": 10.0, "industry": "X"},
        {"ticker": "B", "weight": 0.5, "industry": "X"},  # 缺 return_pct
    ]
    r = build_returns_attribution(h)
    assert r["n_missing_return"] == 1
    assert "B" in r["missing_return_tickers"]
    row_b = next(c for c in r["contribution_table"] if c["ticker"] == "B")
    assert row_b["needs_price"] is True
    assert row_b["return_pct"] is None
    assert row_b["contribution_pct"] == 0.0
    # 缺失只按 0 计，总收益 = 0.5*10 = 5
    assert abs(r["total_return"] - 5.0) < 1e-6


# ─── benchmark 超额 ──────────────────────────────────────────────

def test_benchmark_excess():
    r = build_returns_attribution(_holdings(), benchmark_return=5.0)
    assert r["benchmark"] is not None
    assert abs(r["benchmark"]["excess_return_pct"] - 3.5) < 1e-6  # 8.5 - 5
    assert r["benchmark"]["outperform"] is True


def test_no_benchmark_is_none():
    r = build_returns_attribution(_holdings())
    assert r["benchmark"] is None


# ─── 流派归因（仅当带 school）────────────────────────────────────

def test_school_attribution_when_present():
    h = [
        {"ticker": "A", "weight": 0.5, "return_pct": 10.0, "industry": "X", "school": "成长"},
        {"ticker": "B", "weight": 0.5, "return_pct": 20.0, "industry": "Y", "school": "价值"},
    ]
    r = build_returns_attribution(h)
    assert len(r["school_attribution"]) == 2
    sch_sum = sum(s["contribution_pct"] for s in r["school_attribution"])
    assert abs(sch_sum - r["total_return"]) < 1e-6


# ─── 空 holdings 容错 ────────────────────────────────────────────

def test_empty_holdings():
    r = build_returns_attribution([])
    assert r["total_return"] == 0.0
    assert r["contribution_table"] == []
    assert "error" in r


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
