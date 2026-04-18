"""Regression tests for v2.12.1 · 4 data quality fixes.

Background (2026-04-18 用户在 300308.SZ 报告里发现):
1. 4_peers.peer_table: [] (push2 挂了无 fallback)
2. 7_industry.growth/tam/penetration 永远 "—"（snippets 有数据但未抽取）
3. 8_materials.core_material = "类型；类型" (MX API 垃圾未过滤)
4. BCG 所有股都 Dog（market_share/industry_growth 硬编默认 10）

All tests mock network calls — zero real network dependency.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


# ─── Bug 3 · _is_junk_autofill 校验 ────────────────────────────────

def test_junk_autofill_catches_type_duplication():
    """'类型；类型' 这种 MX prompt 残留必须被识别为垃圾."""
    import importlib
    import run_real_test as rrt
    importlib.reload(rrt)
    assert rrt._is_junk_autofill("类型；类型") is True
    assert rrt._is_junk_autofill("类型；类型；类型") is True


def test_junk_autofill_catches_refusal():
    """LLM 道歉/不知道 应被识别为垃圾."""
    import run_real_test as rrt
    assert rrt._is_junk_autofill("抱歉，我无法回答这个问题") is True
    assert rrt._is_junk_autofill("暂无数据") is True
    assert rrt._is_junk_autofill("") is True
    assert rrt._is_junk_autofill("abc") is True  # 太短


def test_junk_autofill_lets_real_text_through():
    """真实数据不能误伤."""
    import run_real_test as rrt
    assert rrt._is_junk_autofill("光模块 800G 需求爆发，2026 年增速 35%") is False
    assert rrt._is_junk_autofill("中际旭创主要原材料包括光芯片、PCB、玻璃透镜") is False


# ─── Bug 2 · fetch_industry regex 抽取 ─────────────────────────────

def test_industry_growth_regex_picks_context_aware():
    """含'增速/CAGR' 关键词附近的 % 应被优先抽取."""
    import fetch_industry
    # 构造 search_trusted 返回的 snippets
    fake_bodies = [
        {"title": "T1", "body": "某公司 PE 25%（不是增速）", "url": ""},
        {"title": "T2", "body": "光模块行业增速 42% 预计 CAGR 30%", "url": ""},
    ]

    def fake_search(q, **_kw):
        return fake_bodies

    with patch("lib.web_search.search_trusted", side_effect=fake_search):
        result = fetch_industry._dynamic_industry_overview("光模块")
    # 应抓到含"增速"/"CAGR" 上下文的值 (42 或 30)，不是 25
    gh = result.get("growth_heuristic", "")
    assert "—" != gh, f"should extract growth from context-aware pattern; got {gh!r}"
    assert "25%" not in gh, f"should not grab irrelevant PE 25%; got {gh!r}"


def test_industry_penetration_regex_extracts():
    """渗透率 regex 必须抽到值."""
    import fetch_industry
    fake_bodies = [
        {"title": "T", "body": "AI 光模块在数据中心的渗透率 30% 预计 2027 年达 50%", "url": ""},
    ]
    with patch("lib.web_search.search_trusted", return_value=fake_bodies):
        result = fetch_industry._dynamic_industry_overview("光模块")
    pen = result.get("penetration_heuristic", "—")
    assert pen != "—", f"penetration_heuristic should extract; got {pen!r}"
    # 30 或 50 都可接受
    assert any(str(n) in pen for n in (30, 50)), f"should contain 30 or 50; got {pen!r}"


def test_industry_penetration_fallback_wired_in_main():
    """main() 的 penetration 字段必须 fallback 到 dynamic.penetration_heuristic."""
    src = (SCRIPTS / "fetch_industry.py").read_text(encoding="utf-8")
    # line 187 应该包含 dynamic.get("penetration_heuristic")
    assert 'dynamic.get("penetration_heuristic")' in src, (
        "fetch_industry.main() penetration 必须有 dynamic 兜底（v2.12.1）"
    )


# ─── Bug 4 · BCG 真实计算 + 阈值 ───────────────────────────────────

def test_stock_features_market_share_real_computation():
    """market_share 必须真实计算 = 公司市值 / 行业总市值 × 100 (不能硬编默认 10)."""
    src = (SCRIPTS / "lib" / "stock_features.py").read_text(encoding="utf-8")
    # v2.12.1 应该读 cninfo_metrics.total_mcap_yi
    assert "cninfo_metrics" in src, "market_share 计算需读 industry.cninfo_metrics.total_mcap_yi"
    assert 'default=10)' not in src.split('market_share')[1][:200] if 'market_share' in src else True, (
        "不能再用 default=10 硬编"
    )


def test_bcg_thresholds_updated_for_realistic_a_share():
    """BCG Star 阈值必须从 share>15 下调到 >3（A 股极少单股过 15%）."""
    src = (SCRIPTS / "lib" / "deep_analysis_methods.py").read_text(encoding="utf-8")
    # 必须有 share > 3 的分支
    assert "market_share > 3" in src, "Star/Cash Cow 阈值必须下调到 market_share > 3"
    # growth 门槛应该是 > 15 (A 股成长期线)
    assert "market_growth > 15" in src, "growth 阈值应调到 15 (v2.12.1)"
    # 旧的 15 阈值不应再出现在 BCG 判定里
    bcg_section = src[src.find("# BCG") : src.find("# BCG") + 800] if "# BCG" in src else ""
    assert "> 15" not in bcg_section or "market_share > 15" not in bcg_section, (
        "BCG 旧阈值 > 15 不应再出现"
    )


def test_bcg_classifies_zhongji_as_star():
    """中际旭创典型数据（share 5.5, growth 25）应归为 Star."""
    import importlib
    from lib import deep_analysis_methods
    importlib.reload(deep_analysis_methods)
    features = {
        "market_share": 5.5,
        "industry_growth": 25.0,
    }
    # 构造最小 raw_data 以满足 build_competitive_analysis
    raw = {"dimensions": {"14_moat": {"data": {"scores": {}}}}}
    result = deep_analysis_methods.build_competitive_analysis(features, raw)
    bcg = result.get("bcg_position", {}).get("category", "")
    assert "Star" in bcg, f"中际旭创典型 5.5%/25% 应归 Star，got {bcg}"


def test_bcg_classifies_low_growth_small_share_as_dog():
    """真正的 Dog（低份额 + 低增长）仍应识别（回归护栏）."""
    from lib import deep_analysis_methods
    features = {"market_share": 0.5, "industry_growth": 2.0}
    raw = {"dimensions": {"14_moat": {"data": {"scores": {}}}}}
    result = deep_analysis_methods.build_competitive_analysis(features, raw)
    bcg = result.get("bcg_position", {}).get("category", "")
    assert "Dog" in bcg, f"低份额+低增长应归 Dog，got {bcg}"


def test_bcg_question_mark_for_high_growth_small_share():
    """低份额 + 高增长 → Question Mark."""
    from lib import deep_analysis_methods
    features = {"market_share": 1.0, "industry_growth": 25.0}
    raw = {"dimensions": {"14_moat": {"data": {"scores": {}}}}}
    result = deep_analysis_methods.build_competitive_analysis(features, raw)
    bcg = result.get("bcg_position", {}).get("category", "")
    assert "Question" in bcg or "问号" in bcg, f"高增长+低份额应归 Question Mark，got {bcg}"


# ─── Bug 1 · fetch_peers Tier 4 保底 ───────────────────────────────

def test_fetch_peers_has_self_only_fallback():
    """push2 挂了时至少返回公司自己一行 + fallback: True (不再整表空)."""
    src = (SCRIPTS / "fetch_peers.py").read_text(encoding="utf-8")
    assert "_build_self_only_table" in src, "必须有 self-only 兜底函数"
    assert "Tier 4" in src or "self-only fallback" in src, "必须有 Tier 4 保底逻辑"


def test_fetch_peers_tier_chain_documented():
    """fetch_peers 必须有三层 fallback 链结构."""
    src = (SCRIPTS / "fetch_peers.py").read_text(encoding="utf-8")
    assert "Tier 1" in src and "Tier 2" in src, "必须有 Tier 1/2 retry 结构"
    assert "Tier 3" in src, "必须有 Tier 3 雪球浏览器 opt-in 兜底"


def test_fetch_peers_fallback_reason_surfaced():
    """data.fallback_reason 字段必须存在让 agent 识别降级原因."""
    src = (SCRIPTS / "fetch_peers.py").read_text(encoding="utf-8")
    assert '"fallback_reason"' in src, "fallback_reason 字段必须透明暴露"


def test_xueqiu_browser_has_fetch_peers_function():
    """lib/xueqiu_browser.py 必须导出 fetch_peers_via_browser."""
    src = (SCRIPTS / "lib" / "xueqiu_browser.py").read_text(encoding="utf-8")
    assert "def fetch_peers_via_browser" in src, (
        "xueqiu_browser 必须有 fetch_peers_via_browser 供 fetch_peers.py Tier 3 调用"
    )


def test_xueqiu_browser_peer_fn_respects_opt_in():
    """fetch_peers_via_browser 未 opt-in（UZI_XQ_LOGIN!=1）时必须返 []."""
    import os
    # Ensure opt-in disabled
    os.environ.pop("UZI_XQ_LOGIN", None)
    import importlib
    import lib.xueqiu_browser as xb
    importlib.reload(xb)
    result = xb.fetch_peers_via_browser("300308")
    assert result == [], f"未 opt-in 时必须返 []，got {result!r}"
