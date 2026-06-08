"""Tests for 重磅角色 Serenity (H 组 · AI 卡位/瓶颈猎手).

核心命题：Serenity 对一只票的态度，由「该股产品在当前 AI 浪潮里有没有卡位」决定。
- AI 链 + 不可替代 + 中小市值 → bullish（重仓）
- 不在 AI 链上（白酒/银行/传统制造）→ bearish（不碰），无论护城河/需求多好
- 在 AI 链但卡位不够硬 → neutral（待验证）

同时验证：
- 注册完整性：db=52 / criteria / personas / profile / market_scope 都含 serenity
- 派生特征 ai_chokepoint_score / ai_chain_hit / ai_irreplaceable / ai_smallcap 正确
- --school H 锁定时仅 Serenity 参与
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def _raw(name, industry, mcap_yi, chain_txt, switching, scale,
         events=None, policy="积极支持", growth="35%"):
    """构造最小 raw dimensions 给 extract_features."""
    return {"ticker": "TEST.US", "dimensions": {
        "0_basic": {"data": {"name": name, "industry": industry,
                              "market_cap": f"{mcap_yi}亿", "price": "50"}},
        "5_chain": {"data": {"desc": chain_txt}},
        "7_industry": {"data": {"growth": growth}},
        "14_moat": {"data": {"scores": {"switching": switching, "scale": scale,
                                         "intangible": 5, "network": 3}}},
        "13_policy": {"data": {"policy_dir": policy}},
        "15_events": {"data": {"event_timeline": events or []}},
    }}


def _features(*args, **kwargs):
    from lib.stock_features import extract_features
    return extract_features(_raw(*args, **kwargs), {})


# ─── 注册完整性 ──────────────────────────────────────────────────

def test_registered_everywhere():
    # 注意：不硬编码评委总数——总数随其它流派增减演进。这里只验证 Serenity 自身齐全。
    from lib.investor_db import by_id
    from lib.investor_criteria import INVESTOR_RULES
    from lib.investor_personas import PERSONAS
    from lib.investor_profile import get_profile
    from lib.investor_knowledge import MARKET_SCOPE
    from lib.investor_evaluator import SCHOOL_LABELS

    s = by_id("serenity")
    assert s and s["group"] == "I" and s.get("tier") == "flagship"
    assert "serenity" in INVESTOR_RULES and len(INVESTOR_RULES["serenity"]) == 5
    assert "serenity" in PERSONAS
    assert get_profile("serenity", "H")["time_horizon"] != "—"
    assert MARKET_SCOPE.get("serenity") == "all"
    assert SCHOOL_LABELS.get("H")


# ─── 派生特征 ────────────────────────────────────────────────────

def test_feature_chokepoint_smallcap():
    f = _features("AXT科技", "磷化铟InP衬底/光模块", 80,
                  "磷化铟 InP 衬底 光模块 CPO 上游", 9, 8, ["大订单", "缺货涨价"])
    assert f["ai_chain_hit"] is True
    assert f["ai_irreplaceable"] is True
    assert f["ai_smallcap"] is True
    assert f["ai_chokepoint_score"] >= 70


def test_feature_non_ai_zero():
    f = _features("某白酒", "白酒饮料", 20000, "高粱 酿造 经销商", 9, 9)
    assert f["ai_chain_hit"] is False
    assert f["ai_chokepoint_score"] < 40


# ─── 卡位决定态度 · 端到端打分 ────────────────────────────────────

def test_bullish_on_ai_chokepoint_smallcap():
    from lib.investor_evaluator import evaluate
    f = _features("AXT科技", "磷化铟InP衬底/光模块", 80,
                  "磷化铟 InP 衬底 光模块 CPO 上游", 9, 8, ["大订单", "缺货涨价"])
    r = evaluate("serenity", f)
    assert r["signal"] == "bullish"
    assert r["score"] >= 65


def test_bearish_on_non_ai_regardless_of_moat():
    """非 AI 链：即便护城河/需求都好，Serenity 也不碰 → bearish."""
    from lib.investor_evaluator import evaluate
    for name, ind, mc, chain in [
        ("某白酒", "白酒饮料", 20000, "高粱 酿造 经销商"),
        ("小盘银行", "银行", 60, "存款 贷款"),
    ]:
        f = _features(name, ind, mc, chain, 9, 9)  # 故意给高护城河
        r = evaluate("serenity", f)
        assert r["signal"] == "bearish", f"{name} 应 bearish 实际 {r['signal']}"


def test_neutral_on_ai_chain_but_weak_chokepoint():
    """在 AI 链上但市值大/不可替代性弱 → 待验证 neutral."""
    from lib.investor_evaluator import evaluate
    f = _features("某光模块龙头", "光模块", 1500, "光模块 组装", 4, 5)
    r = evaluate("serenity", f)
    assert r["signal"] == "neutral"


def test_ar_optics_detected_in_ai_chain():
    """BUG 回归（v3.6.3）：AR/消费/车载光学不能被误判为「不在 AI 链」。

    水晶光电式标的（光学光电子 · AR/VR + 相机模组 · 404 亿）必须 ai_chain_hit=True
    且落 neutral（在链但卡位不够硬），而不是 bearish/0。
    """
    from lib.investor_evaluator import evaluate
    f = _features("水晶光电式", "光学光电子", 404,
                  "光波导 滤光片 相机模组 AR/VR 车载光学 薄膜光学", 5, 6,
                  growth="30%")
    assert f["ai_chain_hit"] is True, "AR/光学族关键词必须命中 AI 链"
    r = evaluate("serenity", f)
    assert r["signal"] == "neutral", f"应 neutral（在链但非卡点），实际 {r['signal']}"


# ─── --school I 锁定 (Serenity 独立成组) ──────────────────────────

def test_school_lock_I_only_serenity():
    from lib.investor_evaluator import evaluate
    f = _features("AXT科技", "磷化铟InP衬底/光模块", 80,
                  "磷化铟 InP 衬底 光模块 CPO 上游", 9, 8)
    os.environ["UZI_SCHOOL"] = "I"
    try:
        r_s = evaluate("serenity", f)
        r_b = evaluate("buffett", f)
        assert r_s["signal"] != "skip"            # I 派评委(Serenity)参与
        assert r_b["signal"] == "skip"            # 非 I 派被锁定 skip
    finally:
        os.environ.pop("UZI_SCHOOL", None)


# ─── issue #72 · 具身智能 / 人形机器人卡位链 ──────────────────────

def test_embodied_ai_harmonic_reducer_bullish():
    """issue #72 · 绿的谐波(谐波减速器) 是具身智能卡脖子点 · Serenity 本人推过 ·
    小盘 + 高切换成本 + 量产/定点硬证据 → 必须 bullish · 不能再判 0。
    v3.8.0: 真实的绿的谐波有量产/定点(公开)→ 证据 strong → 卡位分高。"""
    from lib.investor_evaluator import evaluate
    f = _features("绿的谐波", "谐波减速器/工业机器人零部件", 250,
                  "人形机器人核心部件 谐波减速器 国产替代 特斯拉定点 量产交付 供应链",
                  switching=9, scale=8, growth="40%", events=["大订单", "量产"])
    assert f["ai_chain_hit"] is True, "谐波减速器/人形机器人必须命中 AI 链(具身智能)"
    assert f["ai_chokepoint_score"] >= 70, f"卡位分应 ≥70，实际 {f['ai_chokepoint_score']}"
    r = evaluate("serenity", f)
    assert r["signal"] == "bullish", f"具身智能卡点应 bullish，实际 {r['signal']}"


def test_embodied_ai_screw_and_sensor_hit_chain():
    """行星滚柱丝杠 / 六维力传感器 等具身智能上游核心件也应命中 AI 链。"""
    for name, ind, chain in [
        ("贝斯特", "行星滚柱丝杠", "人形机器人 行星滚柱丝杠 丝杠"),
        ("柯力传感", "六维力传感器", "六维力 力传感器 机器人 触觉传感器"),
        ("鸣志电器", "空心杯电机", "空心杯电机 无框力矩电机 机器人执行器"),
    ]:
        f = _features(name, ind, 200, chain, switching=8, scale=7, growth="35%")
        assert f["ai_chain_hit"] is True, f"{name} 应命中具身智能链 · 实际未命中"


def test_large_cap_robot_assembler_not_overscored():
    """大盘机器人整机(低切换/低规模) · 命中关键词但卡位不硬 → 不应满分。
    验证关键词扩列没有"开闸放水"——卡位 gating 仍生效。"""
    from lib.investor_evaluator import evaluate
    f = _features("某机器人整机大厂", "工业机器人整机", 3000,
                  "机器人整机组装", switching=3, scale=4, growth="15%")
    r = evaluate("serenity", f)
    assert r["signal"] != "bullish", f"大盘整机卡位不硬 · 不应 bullish · 实际 {r['signal']}"
    assert f["ai_chokepoint_score"] < 60, f"卡位分应 <60，实际 {f['ai_chokepoint_score']}"


def test_baijiu_still_excluded_after_robotics_kw():
    """加机器人关键词后 · 白酒仍必须 0(不在 AI 链) · 防误伤。"""
    from lib.investor_evaluator import evaluate
    f = _features("贵州茅台", "白酒", 23000, "白酒酿造产业链",
                  switching=9, scale=9, growth="12%")
    assert f["ai_chain_hit"] is False
    r = evaluate("serenity", f)
    assert r["signal"] == "bearish" and r["score"] == 0


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
