from dataclasses import replace
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.stock_strategy import rank_overnight_stocks
from .fixtures import stock_context


def with_research_evidence(context, **evidence):
    metadata = dict(context.metadata)
    metadata["research_evidence"] = evidence
    return replace(context, metadata=metadata)


def valid_stocks(count: int):
    return [
        stock_context(
            f"{600000 + index:06d}.SH", price=10.0 + index, name=f"S{index}"
        )
        for index in range(count)
    ]


def test_stock_strategy_filters_st_limit_and_unaffordable_lots():
    valid = stock_context(
        "600406.SH", price=25.0, name="国电南瑞", tail_return_pct=1.0
    )
    st = stock_context("000001.SZ", price=10.0, name="ST样本", is_st=True)
    near_limit = stock_context(
        "000002.SZ",
        price=10.95,
        name="涨停样本",
        pre_close=10.0,
        limit_up=11.0,
    )
    expensive = stock_context("600519.SH", price=1600.0, name="高价样本")
    candidates, rejected = rank_overnight_stocks(
        [st, near_limit, expensive, valid], DecisionConfig()
    )
    assert [candidate.instrument_id for candidate in candidates] == ["600406.SH"]
    assert "st_or_delisting" in rejected["000001.SZ"]
    assert "near_unbuyable_limit" in rejected["000002.SZ"]
    assert "minimum_lot_exceeds_cap" in rejected["600519.SH"]


def test_stock_strategy_uses_configured_cap_when_cash_is_missing():
    affordable = stock_context("600406.SH", price=100.0, name="fixture-stock")

    candidates, rejected = rank_overnight_stocks(
        [affordable], DecisionConfig(available_cash_cny=None)
    )

    assert [candidate.instrument_id for candidate in candidates] == ["600406.SH"]
    assert rejected == {}


def test_explicit_uzi_block_cannot_be_recovered_by_high_tail_momentum():
    context = stock_context(
        "300170.SZ", price=18.0, name="汉得信息", tail_return_pct=9.0
    )
    context = with_research_evidence(
        context,
        uzi_state="blocked",
        uzi_score=90.0,
        uzi_coverage=0.70,
    )

    candidates, rejected = rank_overnight_stocks((context,), DecisionConfig())

    assert candidates == []
    assert "uzi_review_blocked" in rejected["300170.SZ"]


def test_missing_uzi_is_audited_but_not_a_hard_reject():
    context = stock_context("300253.SZ", price=7.9, name="卫宁健康")

    candidates, rejected = rank_overnight_stocks((context,), DecisionConfig())

    assert [item.instrument_id for item in candidates] == ["300253.SZ"]
    assert "uzi_unavailable" in candidates[0].reasons
    assert rejected == {}


def test_candidate_emits_compact_valid_research_evidence_reasons():
    context = with_research_evidence(
        stock_context("300759.SZ", price=18.0, name="康龙化成"),
        ai_score=82.0,
        uzi_score=71.0,
        uzi_coverage=0.68,
        uzi_state="approved",
        source_dates=("2026-08-05",),
        reasons=("uzi_cache_fresh",),
    )

    candidates, rejected = rank_overnight_stocks((context,), DecisionConfig())

    assert candidates[0].reasons[-5:] == (
        "ai_discovery_score:82.0",
        "uzi_score:71.0",
        "uzi_coverage:0.68",
        "evidence_date:2026-08-05",
        "evidence_reason:uzi_cache_fresh",
    )
    assert rejected == {}


def test_malformed_research_evidence_is_audited_without_positive_claims():
    context = stock_context("300759.SZ", price=18.0, name="康龙化成")
    metadata = dict(context.metadata)
    metadata["research_evidence"] = ["not", "a", "mapping"]
    context = replace(context, metadata=metadata)

    candidates, rejected = rank_overnight_stocks((context,), DecisionConfig())

    assert [item.instrument_id for item in candidates] == ["300759.SZ"]
    assert "uzi_unavailable" in candidates[0].reasons
    assert not any(reason.startswith("uzi_score:") for reason in candidates[0].reasons)
    assert rejected == {}


def test_stock_ranker_returns_at_most_three_candidates_by_default():
    candidates, rejected = rank_overnight_stocks(valid_stocks(10), DecisionConfig())

    assert len(candidates) == 3
    assert len(rejected) == 7
