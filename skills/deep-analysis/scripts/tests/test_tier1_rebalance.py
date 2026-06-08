"""Tests for 组合再平衡 (lib/tier1/rebalance.py).

核心命题：
  · 漂移计算正确 (当前 vs 目标，单位百分点)
  · 仅对超阈值持仓出交易，方向正确 (超配→SELL / 低配→BUY)
  · 换手成本分市场估算 (A 股卖出印花税 0.05% + 佣金；港股印花税 0.1% 双边；美股≈0)
  · 默认 targets=None → 等权
  · 不做 TLH，且美股持仓触发税损一句话提示
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from lib.tier1.rebalance import build_rebalance, STAMP_DUTY, COMMISSION


def _holdings():
    """40/35/25 组合 · A+A+HK · 等权目标下 600519 超配、00700 低配."""
    return [
        {"ticker": "600519.SH", "weight": 0.40, "market": "A", "industry": "白酒",
         "value": 400000, "price": 1500},
        {"ticker": "000858.SZ", "weight": 0.35, "market": "A", "industry": "白酒",
         "value": 350000, "price": 150},
        {"ticker": "00700.HK", "weight": 0.25, "market": "HK", "industry": "互联网",
         "value": 250000, "price": 400},
    ]


# ─── 漂移计算 ────────────────────────────────────────────────────

def test_default_equal_weight_targets():
    out = build_rebalance(_holdings(), targets=None)
    assert "等权" in out["summary"]["target_mode"]
    dt = {d["ticker"]: d for d in out["drift_table"]}
    # 等权目标 = 1/3 ≈ 0.3333（输出保留 4 位小数）
    assert abs(dt["600519.SH"]["target_weight"] - 1 / 3) < 1e-3
    # 600519 当前 40% vs 目标 33.3% → 漂移 +6.67pp
    assert abs(dt["600519.SH"]["drift_pp"] - 6.67) < 0.05
    # 00700 当前 25% vs 目标 33.3% → 漂移 -8.33pp
    assert abs(dt["00700.HK"]["drift_pp"] - (-8.33)) < 0.05


def test_threshold_breach_flags():
    out = build_rebalance(_holdings(), drift_threshold=5.0)
    dt = {d["ticker"]: d for d in out["drift_table"]}
    assert dt["600519.SH"]["breached"] is True   # +6.67 > 5
    assert dt["00700.HK"]["breached"] is True     # -8.33 > 5
    assert dt["000858.SZ"]["breached"] is False   # +1.67 < 5
    # 高阈值 → 全部不动
    out2 = build_rebalance(_holdings(), drift_threshold=10.0)
    assert out2["summary"]["any_breach"] is False
    assert out2["summary"]["n_trades"] == 0


def test_explicit_targets_normalized():
    # 给百分数目标，应自动归一化
    targets = {"600519.SH": 50, "000858.SZ": 30, "00700.HK": 20}
    out = build_rebalance(_holdings(), targets=targets)
    dt = {d["ticker"]: d for d in out["drift_table"]}
    assert abs(dt["600519.SH"]["target_weight"] - 0.50) < 1e-6
    # 当前 40 vs 目标 50 → -10pp 低配 → 买
    assert dt["600519.SH"]["drift_pp"] < 0
    assert dt["600519.SH"]["direction"] == "低配→买"


# ─── 交易清单 ────────────────────────────────────────────────────

def test_trades_direction_and_shares():
    out = build_rebalance(_holdings(), drift_threshold=5.0)
    tr = {t["ticker"]: t for t in out["trades"]}
    # 超配 → SELL
    assert tr["600519.SH"]["action"] == "SELL"
    assert tr["600519.SH"]["action_cn"] == "卖出"
    # 低配 → BUY
    assert tr["00700.HK"]["action"] == "BUY"
    # 000858 未超阈值 → 不出现在交易清单
    assert "000858.SZ" not in tr
    # A 股股数按手 (100) 取整
    assert tr["600519.SH"]["est_shares"] % 100 == 0
    # 金额 = |target-current| * total_value；total=1,000,000
    # 600519 漂移 +6.67pp → 卖出约 66,667
    assert 60000 < tr["600519.SH"]["amount"] < 72000


def test_no_value_means_no_amount():
    holdings = [
        {"ticker": "600519.SH", "weight": 0.60, "market": "A"},
        {"ticker": "000858.SZ", "weight": 0.40, "market": "A"},
    ]
    out = build_rebalance(holdings, drift_threshold=5.0)
    assert out["turnover_cost"]["has_value_input"] is False
    for t in out["trades"]:
        assert t["amount"] is None
        assert t["est_shares"] is None
    assert out["summary"]["estimated_cost"] is None


# ─── 换手成本 ────────────────────────────────────────────────────

def test_turnover_cost_by_market():
    out = build_rebalance(_holdings(), drift_threshold=5.0)
    tc = out["turnover_cost"]
    assert tc["has_value_input"] is True
    assert tc["total_cost"] > 0
    # A 股卖出: 印花税 0.05% + 佣金 0.025%
    a = tc["by_market"]["A"]
    # 600519 卖出约 66,667 → 印花税 ≈ 33.3, 佣金 ≈ 16.7
    expected_stamp = a["turnover"] * STAMP_DUTY["A"]
    assert abs(a["stamp_duty"] - expected_stamp) < 1.0
    expected_comm = a["turnover"] * COMMISSION["A"]
    assert abs(a["commission"] - expected_comm) < 1.0


def test_hk_stamp_higher_than_a():
    # 港股印花税率 0.1% > A 股 0.05%
    assert STAMP_DUTY["HK"] > STAMP_DUTY["A"]
    assert STAMP_DUTY["US"] == 0.0


# ─── 集中度 ──────────────────────────────────────────────────────

def test_concentration_drops_after_equal_weight():
    out = build_rebalance(_holdings(), targets=None)
    conc = out["concentration"]
    # 等权后最大单只 (40%→33.3%) 下降
    assert conc["max_single_change_pp"] < 0
    # HHI 等权后下降（更分散）
    assert conc["hhi_change"] < 0


# ─── 不做 TLH + 美股提示 ─────────────────────────────────────────

def test_no_tlh_a_hk_only():
    out = build_rebalance(_holdings())
    note = out["summary"]["tlh_note"]
    assert "不做" in note and "TLH" in note
    assert "美股" not in note or "另议" not in note  # 无美股 → 不出现"另议税损"


def test_us_holding_triggers_tlh_hint():
    holdings = [
        {"ticker": "AAPL", "weight": 0.60, "market": "US", "value": 60000, "price": 200},
        {"ticker": "600519.SH", "weight": 0.40, "market": "A", "value": 40000, "price": 1500},
    ]
    out = build_rebalance(holdings, drift_threshold=5.0)
    assert "美股" in out["summary"]["tlh_note"]
    assert "另议" in out["summary"]["tlh_note"]
    # 美股交易换手成本印花税应为 0
    if "US" in out["turnover_cost"]["by_market"]:
        assert out["turnover_cost"]["by_market"]["US"]["stamp_duty"] == 0.0


# ─── 边界 ────────────────────────────────────────────────────────

def test_empty_holdings():
    out = build_rebalance([])
    assert "error" in out


def test_methodology_log_present():
    out = build_rebalance(_holdings())
    assert isinstance(out["methodology_log"], list)
    assert len(out["methodology_log"]) >= 5


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
