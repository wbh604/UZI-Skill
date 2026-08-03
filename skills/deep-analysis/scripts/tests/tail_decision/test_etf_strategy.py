from dataclasses import replace
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.etf_strategy import rank_etfs
from .fixtures import etf_context


def test_etf_strategy_rejects_low_liquidity_and_ranks_tail_strength():
    strong = etf_context(
        "513050.SH",
        amount=2_000_000_000,
        tail_return_pct=1.2,
        vwap_distance_pct=0.4,
        quality="pass",
    )
    weak = etf_context(
        "513180.SH",
        amount=1_500_000_000,
        tail_return_pct=0.2,
        vwap_distance_pct=0.1,
        quality="pass",
    )
    illiquid = etf_context(
        "560000.SH",
        amount=10_000_000,
        tail_return_pct=3.0,
        vwap_distance_pct=1.0,
        quality="pass",
    )
    candidates, rejected = rank_etfs(
        [weak, illiquid, strong], DecisionConfig()
    )
    assert [candidate.instrument_id for candidate in candidates] == [
        "513050.SH",
        "513180.SH",
    ]
    assert "low_turnover" in rejected["560000.SH"]


def test_etf_strategy_accepts_tracking_target_metadata_alias():
    context = etf_context(
        "513050.SH",
        amount=2_000_000_000,
        tail_return_pct=1.2,
        vwap_distance_pct=0.4,
        quality="pass",
    )
    metadata = dict(context.metadata)
    metadata["tracking_target"] = metadata.pop("tracking_index")
    metadata.pop("theme")
    candidates, rejected = rank_etfs(
        [replace(context, metadata=metadata)], DecisionConfig()
    )
    assert [candidate.instrument_id for candidate in candidates] == ["513050.SH"]
    assert rejected == {}
