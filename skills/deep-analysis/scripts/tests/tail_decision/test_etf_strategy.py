from dataclasses import replace
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.etf_strategy import rank_etfs
from lib.tail_decision.stock_strategy import rank_overnight_stocks
from .fixtures import etf_context, stock_context


def valid_etfs(count: int):
    return [
        etf_context(
            f"{510000 + index:06d}.SH",
            amount=2_000_000_000.0,
            tail_return_pct=1.2,
            vwap_distance_pct=0.4,
            quality="pass",
        )
        for index in range(count)
    ]


def valid_stocks(count: int):
    return [
        stock_context(
            f"{600000 + index:06d}.SH", price=10.0 + index, name=f"S{index}"
        )
        for index in range(count)
    ]


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


def test_default_ranker_limits_produce_at_most_five_finalists():
    config = DecisionConfig()
    stocks, _ = rank_overnight_stocks(tuple(valid_stocks(10)), config)
    etfs, _ = rank_etfs(tuple(valid_etfs(10)), config)

    assert len(stocks) == 3
    assert len(etfs) == 2
    assert len(stocks) + len(etfs) == 5
