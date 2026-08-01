# -*- coding: utf-8 -*-
"""缺陷2 回归测试：做空派(burry/chanos) 的 bullish 不再污染 long-book 共识。
v2.15.6
"""
from lib.investor_db import INVESTORS, by_id
from lib.investor_evaluator import panel_summary


def test_short_sellers_have_mandate():
    for iid in ("burry", "chanos"):
        inv = by_id(iid)
        assert inv is not None, f"{iid} 缺失"
        assert inv.get("mandate") == "short", f"{iid} 应有 mandate=short"


def test_only_two_short_sellers():
    shorts = [i["id"] for i in INVESTORS if i.get("mandate") == "short"]
    assert set(shorts) == {"burry", "chanos"}


def test_panel_summary_excludes_short_from_long_book():
    # 模拟：64 位 long 派中 10 位 bullish；burry/chanos 也 bullish（=无做空逻辑）
    others = [i["id"] for i in INVESTORS if i.get("mandate") != "short"]
    assert len(others) == 64, len(others)
    results = {}
    for k in others:
        bull = k in others[:10]
        results[k] = {
            "signal": "bullish" if bull else "bearish",
            "score": 80 if bull else 20,
            "confidence": 70,
            "headline": "x",
        }
    results["burry"] = {"signal": "bullish", "score": 90, "confidence": 80, "headline": "no short thesis"}
    results["chanos"] = {"signal": "bullish", "score": 85, "confidence": 75, "headline": "no short thesis"}
    s = panel_summary(results)
    # long-book bullish 只数 64 人里的 10 个，不含 burry/chanos 的 2 个 bullish
    assert s["bullish"] == 10, s["bullish"]
    assert s["long_active"] == 64, s["long_active"]
    assert s["short_consensus"]["short_candidates"] == 0
    assert s["short_consensus"]["no_short_thesis"] == 2
    assert s["short_consensus"]["total"] == 2


def test_panel_summary_short_candidates_counted():
    others = [i["id"] for i in INVESTORS if i.get("mandate") != "short"]
    results = {k: {"signal": "bearish", "score": 20, "confidence": 60, "headline": "x"} for k in others}
    # 让 chanos 变成 bearish（=可做空候选），burry 仍 bullish
    results["chanos"] = {"signal": "bearish", "score": 15, "confidence": 90, "headline": "fraud red flag"}
    results["burry"] = {"signal": "bullish", "score": 85, "confidence": 70, "headline": "no short thesis"}
    s = panel_summary(results)
    assert s["short_consensus"]["short_candidates"] == 1
    assert s["short_consensus"]["no_short_thesis"] == 1
    # long-book 不应包含任何做空派票
    assert s["bullish"] == 0
    assert s["bearish"] == 64
