"""Regression tests for v2.13.3 · 评委规则历史立场还原.

中际旭创 300308 实测暴露：
- 19 人给 100 分（含 13 位游资 · Lynch / Soros / 段永平 / 张坤 / 邓晓峰 等）
- 木头姐 13 分看空（实际 CPO 是她的赛道）
- 游资 "市值超 80 亿 = 看空" 等反向判定

本测试验证 v2.13.3 修复：
1. 游资射程 · 大市值（> 500 亿默认）应 skip 不是 bullish/bearish
2. 索罗斯反身性方向正确（只做多 upside > 10% · 不把 -63% 也当看多信号）
3. 林奇 PEG < 1 ideal · PE > 40 红线
4. 木头姐字段名修正 + CPO/光模块/算力白名单
5. 段永平/张坤/邓晓峰 PE 红线
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


# ─── Fix 1 · 游资射程 ────────────────────────────────────────────

def test_youzi_out_of_range_for_mega_cap():
    """9456 亿大盘股不在任何常规游资的射程（章盟主 allowlist 除外）."""
    from lib.investor_evaluator import _is_youzi_out_of_range
    features = {"market_cap_yi": 9456, "market_cap": 9456e8, "stage_num": 2}
    # 大部分游资（无 max_mcap 的）都应 skip 超大盘
    out, reason = _is_youzi_out_of_range("sun_ge", features)
    assert out is True
    assert "9456" in reason or "射程" in reason

    out, reason = _is_youzi_out_of_range("zhao_lg", features)
    assert out is True

    out, reason = _is_youzi_out_of_range("fs_wyj", features)  # 佛山无影脚 max_mcap=80 亿
    assert out is True


def test_zhang_mz_allowlist_can_play_mega_cap():
    """章盟主在 allowlist 里 · 9456 亿不应 skip."""
    from lib.investor_evaluator import _is_youzi_out_of_range
    features = {"market_cap_yi": 9456, "market_cap": 9456e8, "stage_num": 2, "trend": "up"}
    out, reason = _is_youzi_out_of_range("zhang_mz", features)
    # 章盟主 fit_rules min_mcap=200 亿 + allowlist 绕过 500 亿隐式上限 · in-range
    assert out is False


def test_youzi_in_range_for_small_cap():
    """50-150 亿小盘股应 in range（常规游资射程内）."""
    from lib.investor_evaluator import _is_youzi_out_of_range
    features = {"market_cap_yi": 100, "market_cap": 100e8, "stage_num": 2, "trend": "up",
                "is_sector_leader": True}
    # sun_ge fit_rules min_mcap=10亿 + needs is_sector_leader
    out, reason = _is_youzi_out_of_range("sun_ge", features)
    assert out is False, f"100 亿 + sector leader 应在 sun_ge 射程, got {reason}"


def test_non_youzi_investor_not_affected():
    """非 F 组（巴菲特等）不受射程检查影响."""
    from lib.investor_evaluator import _is_youzi_out_of_range
    features = {"market_cap_yi": 9456, "market_cap": 9456e8}
    out, _ = _is_youzi_out_of_range("buffett", features)
    assert out is False
    out, _ = _is_youzi_out_of_range("lynch", features)
    assert out is False


# ─── Fix 2 · 索罗斯反身性方向 ────────────────────────────────────

def test_soros_bullish_on_positive_upside():
    """研报目标价 +30% · 做多反身性 pass."""
    from lib.investor_evaluator import evaluate
    features = {
        "market": "A", "ticker": "600519.SH", "name": "贵州茅台", "industry": "白酒",
        "upside_to_target": 30,
        "macro_rate_easing": True,
        "stage_num": 2,
    }
    r = evaluate("soros", features)
    # upside 30% · pass sentiment_long_reflex (4 分) + penalty pass (4 分) + macro (3) + stage (3)
    # = 14/14 = 100 分
    assert r["score"] > 70


def test_soros_bearish_on_extreme_negative_upside():
    """研报目标价 -63%（狂热高位）· 做多方面 fail · 应 bearish or neutral."""
    from lib.investor_evaluator import evaluate
    features = {
        "market": "A", "ticker": "300308.SZ", "name": "中际旭创", "industry": "通信设备",
        "upside_to_target": -63,
        "macro_rate_easing": False,
        "stage_num": 2,
    }
    r = evaluate("soros", features)
    # upside -63% fail sentiment_long_reflex · fail sentiment_short_penalty · pass stage (3)
    # = 3/14 ≈ 21 分 · bearish
    assert r["score"] < 50, f"索罗斯对 -63% upside 应 bearish · got {r['score']}"


def test_soros_neutral_on_small_upside():
    """±10% 以内 · 无反身性机会 · 中性."""
    from lib.investor_evaluator import evaluate
    features = {
        "market": "A", "ticker": "600519.SH", "name": "test", "industry": "white",
        "upside_to_target": 5,
        "macro_rate_easing": False,
        "stage_num": 1,
    }
    r = evaluate("soros", features)
    # upside 5 fail long_reflex · pass penalty (4) · fail macro / stage
    assert r["score"] < 60


# ─── Fix 3 · 林奇 PEG + PE 红线 ─────────────────────────────────

def test_lynch_ideal_peg_under_1():
    """PEG < 1 · 林奇理想 · 高分."""
    from lib.investor_evaluator import evaluate
    features = {
        "market": "A", "ticker": "test", "name": "test", "industry": "消费",
        "pe": 15,
        "revenue_growth_latest": 20,  # PEG = 0.75
        "research_coverage": 10,
        "buy_rating_pct": 70,
    }
    r = evaluate("lynch", features)
    # peg_ideal (5) + pe_not_rolls_royce (3) + fast_grower_zone (3) + understandable (2) + research (2)
    # = 15/18 ≈ 83
    assert r["score"] > 70


def test_lynch_rejects_pe_over_40():
    """PE 63 + 增速 40% · PEG 1.58 · 林奇不会 100 分 · PE 40 红线触发."""
    from lib.investor_evaluator import evaluate
    features = {
        "market": "A", "ticker": "300308.SZ", "name": "中际旭创", "industry": "通信设备",
        "pe": 63,
        "revenue_growth_latest": 40,  # PEG = 1.575 · 超出 1.5
        "research_coverage": 20,
        "buy_rating_pct": 80,
    }
    r = evaluate("lynch", features)
    # peg_ideal fail · peg_acceptable fail (1.575 >= 1.5) · pe_not_rolls_royce fail (63 > 40)
    # · fast_grower_zone pass (40% in 20-50) · understandable pass · research pass
    # = 7/18 ≈ 39 分 · 不是 100！
    assert r["score"] < 50, f"PE 63 林奇应 < 50 分, got {r['score']}"


def test_lynch_peg_acceptable_zone():
    """PEG 1.0-1.5 临界接受."""
    from lib.investor_evaluator import evaluate
    features = {
        "market": "A", "ticker": "test", "name": "test", "industry": "消费",
        "pe": 30,
        "revenue_growth_latest": 25,  # PEG = 1.2 · fast_grower 25 in (20,50)
        "research_coverage": 10,
        "buy_rating_pct": 70,
    }
    r = evaluate("lynch", features)
    # peg_ideal fail · peg_acceptable pass (3) · pe_not_rolls_royce pass (3) ·
    # fast_grower_zone pass (3) · understandable (2) · research (2) = 13/18 ≈ 72
    assert 55 < r["score"] < 85


# ─── Fix 4 · 木头姐 ─────────────────────────────────────────────

def test_wood_bullish_on_cpo_optical_module():
    """中际旭创（CPO/光模块/通信设备/AI 算力）应是木头姐的菜 · 高分看多."""
    from lib.investor_evaluator import evaluate
    features = {
        "market": "A", "ticker": "300308.SZ", "name": "中际旭创", "industry": "通信设备",
        "industry_growth": 40,  # v2.13.3 字段名
        "rev_growth_3y": 50,
        "max_drawdown_1y": -25,
    }
    r = evaluate("wood", features)
    # s_curve pass (40 > 20) · innovation_platform pass ("通信设备" 在白名单)
    # · revenue_acceleration pass · long_term_view pass = 15/15 = 100
    assert r["score"] > 85, f"光模块应是木头姐的菜, got {r['score']}"


def test_wood_uses_industry_growth_not_pct():
    """确保 WOOD_RULES 读 industry_growth（新字段）· 老 industry_growth_pct fallback."""
    from lib.investor_evaluator import evaluate
    # 只提供 industry_growth · 不提供 industry_growth_pct
    features = {
        "market": "A", "ticker": "test", "name": "test", "industry": "AI",
        "industry_growth": 35,  # 新字段
        "rev_growth_3y": 30,
        "max_drawdown_1y": -20,
    }
    r = evaluate("wood", features)
    assert r["score"] > 70, "新字段 industry_growth=35 应 pass s_curve rule"


# ─── Fix 5 · 中国价投派 PE 红线 ─────────────────────────────────

def test_duan_rejects_pe_over_40():
    """段永平 PE 63 应明显扣分."""
    from lib.investor_evaluator import evaluate
    features = {
        "market": "A", "ticker": "300308.SZ", "name": "中际旭创", "industry": "通信设备",
        "pe": 63,
        "net_margin": 28,
        "roe_latest": 44,
        "pe_quantile_5y": 55,  # fail good_price
        "moat_total": 26,
        "consecutive_profit_years": 8,
    }
    r = evaluate("duan", features)
    # good_business pass (5) · good_people pass default (4) · good_price fail (55>50)
    # · pe_not_expensive fail (63>40 · -3) · long_term_clear pass (3) = 12/19 ≈ 63
    # v2.13.3 加 PE 红线扣 3 分 · 原版会是 12/16 = 75
    # 关键：PE 63 导致分数 < 80（不再 100）
    assert r["score"] < 80, f"段永平 PE 63 应扣分，got {r['score']}"


def test_zhangkun_rejects_pe_over_40():
    """张坤 PE 63 应触发估值纪律扣分."""
    from lib.investor_evaluator import evaluate
    features = {
        "market": "A", "ticker": "300308.SZ", "name": "中际旭创", "industry": "通信设备",
        "pe": 63,
        "roe_5y_above_15": 5,
        "net_margin": 25,
        "moat_intangible": 8,
    }
    r = evaluate("zhangkun", features)
    # roe_persistent pass (5) + pricing_power pass (3) + moat_brand pass (3) + pe_discipline fail (3)
    # = 11/14 ≈ 79 分（原来没 pe_discipline 就是 100）
    assert r["score"] < 90, f"张坤 PE 63 应触发估值纪律，got {r['score']}"


def test_value_investors_accept_pe_under_40():
    """PE < 40 价值派应正常高分."""
    from lib.investor_evaluator import evaluate
    features = {
        "market": "A", "ticker": "test", "name": "test", "industry": "白酒",
        "pe": 30,
        "net_margin": 28,
        "roe_latest": 30,
        "roe_5y_above_15": 5,
        "pe_quantile_5y": 30,
        "moat_total": 26,
        "moat_intangible": 9,
        "consecutive_profit_years": 10,
    }
    r1 = evaluate("duan", features)
    r2 = evaluate("zhangkun", features)
    assert r1["score"] > 80, f"段永平 PE 30 应高分, got {r1['score']}"
    assert r2["score"] > 80, f"张坤 PE 30 应高分, got {r2['score']}"
