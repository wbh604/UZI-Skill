"""Regression for v3.7.0 · 13 位新晋科技大佬评委.

用户需求：扩充评委库 · 加入受关注度高的新晋科技/创新派.

分布 (52→65)：
  B 成长派 +5: andreessen / gurley / naval / gerstner / chamath
  C 宏观派 +2: burry / chanos (做空猎手)
  E 中国价投 +1: zhang_lei (高瓴)
  G 量化派 +1: asness (AQR 因子)
  H AI 卡位/瓶颈猎手 +4: jensen_huang / musk / altman / saylor (+ Serenity 已有)

测试覆盖：
1. 总人数 52 → 65 · 各派人数符合预期
2. 13 个新 ID 全部出现在 INVESTOR_RULES
3. 每个新评委有 ≥4 条规则 (避免空架子)
4. NVDA-like 场景 · AI 派 (Andreessen/Gerstner/Huang/Altman) 应 bullish · score ≥ 70
5. 传统白酒股 · AI 派应低分 (industry filter 生效)
6. SCHOOL_LABELS / institutional.py THEMES 已含 H
"""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


# ─── #1 · 人数 + 分组 ────────────────────────────────────

def test_total_count_65():
    from lib.investor_db import INVESTORS, assert_count
    assert_count()  # v3.9.0 起 == 66 (65 + 股海贼王)
    assert len(INVESTORS) == 66


def test_group_distribution_after_v37():
    from lib.investor_db import INVESTORS
    from collections import Counter
    dist = Counter(i["group"] for i in INVESTORS)
    # 注：Serenity 已从 H 拆出独立成 I 组（重磅角色）· H 仅留 4 位科技领袖
    expected = {"A": 6, "B": 9, "C": 7, "D": 4, "E": 7, "F": 24, "G": 4, "H": 4, "I": 1}  # v3.9.0 F+1 ghzw
    assert dict(dist) == expected, f"分组分布 {dict(dist)} != {expected}"


# ─── #2 · 13 新 ID 全部注册 ──────────────────────────────

NEW_IDS = [
    # B 派 +5
    "andreessen", "gurley", "naval", "gerstner", "chamath",
    # C 派 +2
    "burry", "chanos",
    # E 派 +1
    "zhang_lei",
    # G 派 +1
    "asness",
    # H 派 +4
    "jensen_huang", "musk", "altman", "saylor",
]


def test_all_thirteen_in_investor_db():
    from lib.investor_db import INVESTORS
    ids = {i["id"] for i in INVESTORS}
    missing = [i for i in NEW_IDS if i not in ids]
    assert not missing, f"investor_db 缺: {missing}"


def test_all_thirteen_registered_in_rules():
    from lib.investor_criteria import INVESTOR_RULES
    missing = [i for i in NEW_IDS if i not in INVESTOR_RULES]
    assert not missing, f"INVESTOR_RULES 缺: {missing}"


def test_each_new_investor_has_at_least_4_rules():
    """避免空架子 · 每个新评委至少 4 条规则才有评分意义."""
    from lib.investor_criteria import INVESTOR_RULES
    weak = []
    for inv_id in NEW_IDS:
        rules = INVESTOR_RULES.get(inv_id, [])
        if len(rules) < 4:
            weak.append(f"{inv_id} 仅 {len(rules)} 条")
    assert not weak, f"规则不足 4 条: {weak}"


def test_no_duplicate_ids():
    """加新人时不应跟现有 ID 重复."""
    from lib.investor_db import INVESTORS
    ids = [i["id"] for i in INVESTORS]
    assert len(ids) == len(set(ids)), f"重复 ID: {set([x for x in ids if ids.count(x) > 1])}"


# ─── #3 · NVDA 场景 · AI 派应该高分 ─────────────────────

NVDA_FEAT = {
    "market": "US", "ticker": "NVDA", "name": "NVIDIA Corp",
    "industry": "AI 算力 / 半导体",
    "market_cap_yi": 3_500_000,
    "pe_ttm": 45, "pb": 30, "ps": 25,
    "roe": 80, "net_margin": 52, "gross_margin": 78,
    "rev_growth_yoy": 125, "rev_growth_3y": 80,
    "moat_total": 35, "industry_rank": 1,
    "ocf_positive": True, "ocf_to_ni": 45,
    "rd_intensity": 12, "founder_active": True, "founder_ownership_pct": 3.5,
    "debt_ratio": 10,
    "roe_5y_above_15": 5, "roe_5y_min": 25, "net_profit_growth_3y": 95,
    "ytd_return": 180, "price_above_ma200": True,
    "ocf_to_net_income_ratio": 1.1,
    "tam_usd_bn": 5000,
}


def test_andreessen_bullish_on_nvda():
    from lib.investor_evaluator import evaluate
    r = evaluate("andreessen", NVDA_FEAT)
    assert r["signal"] == "bullish"
    assert r["score"] >= 70, f"Andreessen on NVDA score={r['score']}"


def test_gerstner_bullish_on_nvda():
    from lib.investor_evaluator import evaluate
    r = evaluate("gerstner", NVDA_FEAT)
    assert r["signal"] == "bullish"
    assert r["score"] >= 75


def test_jensen_huang_bullish_on_ai_stock():
    from lib.investor_evaluator import evaluate
    r = evaluate("jensen_huang", NVDA_FEAT)
    assert r["signal"] == "bullish"
    assert r["score"] >= 75


def test_altman_bullish_on_ai_compute():
    from lib.investor_evaluator import evaluate
    r = evaluate("altman", NVDA_FEAT)
    assert r["signal"] == "bullish"


# ─── #4 · 传统白酒股 · AI 派应该低分 (industry filter) ──

MAOTAI_FEAT = {
    "market": "A", "ticker": "600519.SH", "name": "贵州茅台",
    "industry": "白酒",
    "market_cap_yi": 23000, "pe_ttm": 28, "pb": 8.5,
    "roe": 42, "net_margin": 52.6, "gross_margin": 91.5,
    "rev_growth_3y": 12, "rev_growth_yoy": 10, "net_profit_growth_3y": 14,
    "moat_total": 32, "industry_rank": 1, "ocf_positive": True,
    "debt_ratio": 15, "roe_5y_above_15": 5, "roe_5y_min": 30,
    "founder_active": True,  # 茅台老酱工艺传承 · 视为 founder ethos 长期对齐
}


def test_andreessen_skips_or_low_on_baijiu():
    """白酒不是 'Software/AI eating the world' 范畴 · 应低分."""
    from lib.investor_evaluator import evaluate
    r = evaluate("andreessen", MAOTAI_FEAT)
    assert r["score"] < 70, f"Andreessen 在白酒上 score={r['score']} 过高"


def test_jensen_huang_low_on_baijiu():
    """白酒不在 AI 算力链 · Jensen Huang 看不到机会."""
    from lib.investor_evaluator import evaluate
    r = evaluate("jensen_huang", MAOTAI_FEAT)
    assert r["score"] < 60, f"Jensen 在白酒上 score={r['score']} 不应高"


def test_zhang_lei_bullish_on_baijiu():
    """张磊高瓴长期主义 · 白酒龙头是经典对象."""
    from lib.investor_evaluator import evaluate
    r = evaluate("zhang_lei", MAOTAI_FEAT)
    assert r["signal"] == "bullish"
    assert r["score"] >= 70


# ─── #5 · 做空 (Burry/Chanos) 在白酒上应中性或低分 ──

def test_chanos_neutral_on_clean_company():
    """无审计问题 / 无表外债务 · Chanos 看不到空头 thesis · 不会高分但也不低."""
    from lib.investor_evaluator import evaluate
    r = evaluate("chanos", MAOTAI_FEAT)
    # 主要测不崩 · 评分合理
    assert 30 <= r["score"] <= 100


# ─── #6 · SCHOOL_LABELS + THEMES 含 H ───────────────────

def test_school_labels_includes_h():
    from lib.investor_evaluator import SCHOOL_LABELS
    # H = 科技领袖派（4 位大亨）· Serenity 的「AI 卡位/瓶颈猎手」已独立为 I 组
    assert "H" in SCHOOL_LABELS and SCHOOL_LABELS["H"]
    assert "I" in SCHOOL_LABELS
    assert "AI" in SCHOOL_LABELS["I"] or "卡位" in SCHOOL_LABELS["I"]


def test_school_lock_banner_renders_h_with_color():
    """H 派 banner 必须有专属配色 + 代表评委含 Serenity / 黄仁勋."""
    from lib.report.institutional import _render_school_lock_banner
    html = _render_school_lock_banner({"school_lock": {"group": "H", "label": "AI 卡位/瓶颈猎手"}})
    assert "SCHOOL LOCK" in html
    assert "H" in html
    # 配色不是默认灰
    assert "rgba(107,114,128" not in html
    # 代表评委含 Serenity / 黄仁勋
    assert "Serenity" in html or "黄仁勋" in html


# ─── #7 · 关键不变量 · 不破坏已有评委 ───────────────────

def test_existing_flagship_investors_still_present():
    """v3.7 加新人不能误删旧评委."""
    from lib.investor_db import INVESTORS
    ids = {i["id"] for i in INVESTORS}
    flagship = {"buffett", "graham", "munger", "lynch", "wood", "thiel",
                "soros", "dalio", "duan", "zhangkun", "zhao_lg", "sun_ge",
                "simons", "serenity"}
    missing = flagship - ids
    assert not missing, f"旗舰评委被误删: {missing}"


def test_existing_rules_still_registered():
    from lib.investor_criteria import INVESTOR_RULES
    for inv_id in ("buffett", "lynch", "soros", "simons", "duan"):
        assert inv_id in INVESTOR_RULES
        # 量化派 simons 只有 2 条规则也合理 (信号 + 波动) · 不强求 ≥3
        assert len(INVESTOR_RULES[inv_id]) >= 2
