"""Tests for tier1/ai_readiness · 单票 AI 就绪度评估。

改编自 anthropics/financial-services private-equity/ai-readiness，
复用 Serenity 的 ai_chokepoint_score 作为卡位强度锚。

两个核心 case：
- AI 卡位强的小盘（AXT 式）→ 评级「强」/「中」、三 gate 全过、Go、有杠杆点
- 非 AI 股（白酒）→ 评级「无」、Gate① 不过、Wait、组合字段 N/A
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.tier1.ai_readiness import build_ai_readiness


def _ai_chokepoint_features():
    """AXT 式：磷化铟衬底 / 光模块上游，小盘 + 不可替代。"""
    return {
        "name": "AXT科技", "code": "AXTI.US", "industry": "磷化铟InP衬底/光模块",
        "market_cap_yi": 80, "moat_total": 26,
        "ai_chokepoint_score": 88.0, "ai_chain_hit": True,
        "ai_chain_keywords": ["inp", "磷化铟", "光模块", "cpo"],
        "ai_irreplaceable": True, "ai_smallcap": True, "industry_growth": 35,
    }


def _non_ai_features():
    """白酒：不在 AI 链上。"""
    return {
        "name": "某白酒", "code": "600XXX.SH", "industry": "白酒饮料",
        "market_cap_yi": 20000, "moat_total": 36,
        "ai_chokepoint_score": 4.0, "ai_chain_hit": False,
        "ai_chain_keywords": [], "ai_irreplaceable": True, "ai_smallcap": False,
        "industry_growth": 8,
    }


def _raw(chain_desc="", events=None, growth="35%"):
    return {"dimensions": {
        "5_chain": {"data": {"desc": chain_desc}},
        "15_events": {"data": {"event_timeline": events or []}},
        "7_industry": {"data": {"growth": growth}},
    }}


# ─── Case 1：AI 卡位强 ────────────────────────────────────────────

def test_strong_ai_chokepoint():
    raw = _raw("磷化铟 InP 衬底 光模块 上游 满产",
               events=["大订单 长协 缺货涨价 扩产 量产"], growth="35%")
    r = build_ai_readiness(_ai_chokepoint_features(), raw)

    # 结构断言
    assert set(["rating", "gates", "leverage_points", "conclusion",
                "methodology_log"]).issubset(r.keys())
    assert isinstance(r["gates"], list) and len(r["gates"]) == 3
    assert isinstance(r["methodology_log"], list) and r["methodology_log"]

    # 关键字段
    assert r["rating"] in ("强", "中")
    assert r["gates_passed"] == 3
    assert r["verdict"].startswith("Go")
    assert r["gaps"] == []
    assert r["ai_chokepoint_score"] == 88.0
    assert len(r["leverage_points"]) >= 1
    # 推断出光互连杠杆点
    cats = [p["category"] for p in r["leverage_points"]]
    assert any("光" in c for c in cats)
    assert r["company"]["name"] == "AXT科技"


# ─── Case 2：非 AI 股 ─────────────────────────────────────────────

def test_non_ai_stock():
    raw = _raw("高粱 酿造 经销商", events=["分红", "提价"], growth="8%")
    r = build_ai_readiness(_non_ai_features(), raw)

    assert r["rating"] == "无"
    # Gate① 必不过；② 真实需求也不成立（不在链上）
    assert r["gates"][0]["pass"] is False
    assert r["gates"][1]["pass"] is False
    assert r["gates_passed"] < 3
    assert r["verdict"].startswith("Wait")
    assert "① 是否真在 AI 产业链上" in r["gaps"]
    # 一句话结论标注 N/A
    assert "N/A" in r["conclusion"]
    # 组合维度字段全 N/A
    assert r["cross_portfolio_ranking"].startswith("N/A")
    assert r["replays"].startswith("N/A")
    assert r["aggregate_ebitda"].startswith("N/A")


# ─── Case 3：在链但卡位不够硬 → 中 / Wait ─────────────────────────

def test_ai_chain_but_weak_chokepoint():
    f = {
        "name": "某光模块组装厂", "code": "300XXX.SZ", "industry": "光模块",
        "market_cap_yi": 1500, "moat_total": 14,
        "ai_chokepoint_score": 52.0, "ai_chain_hit": True,
        "ai_chain_keywords": ["光模块"], "ai_irreplaceable": False,
        "ai_smallcap": False, "industry_growth": 30,
    }
    raw = _raw("光模块 组装", events=["扩产"], growth="30%")
    r = build_ai_readiness(f, raw)
    assert r["rating"] in ("中", "弱")
    assert r["gates_passed"] < 3
    assert r["verdict"].startswith("Wait")
    # Gate③ 不可替代未过 → 在缺口里
    assert "③ 卡位是否不可替代且可持续" in r["gaps"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
