from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.contracts import QualityLevel
from lib.tail_decision.quality import evaluate_quote_quality
from .fixtures import quote


def test_two_fresh_sources_within_point_three_percent_pass():
    first = quote(source="eastmoney", last_price=25.00)
    second = quote(source="tencent", last_price=25.05)
    decision = evaluate_quote_quality(
        first.instrument_id, [first, second], first.fetched_at, DecisionConfig()
    )
    assert decision.level is QualityLevel.PASS


def test_single_source_is_degraded_not_recommendable():
    first = quote(source="eastmoney", last_price=25.00)
    decision = evaluate_quote_quality(
        first.instrument_id, [first], first.fetched_at, DecisionConfig()
    )
    assert decision.level is QualityLevel.DEGRADED
    assert "insufficient_independent_sources" in decision.reasons


def test_stale_or_conflicting_quotes_are_blocked():
    first = quote(source="eastmoney", last_price=25.00)
    stale = replace(
        quote(source="tencent", last_price=25.20),
        fetched_at=first.fetched_at - timedelta(seconds=61),
    )
    decision = evaluate_quote_quality(
        first.instrument_id, [first, stale], first.fetched_at, DecisionConfig()
    )
    assert decision.level is QualityLevel.BLOCKED
