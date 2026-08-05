from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.stock_strategy import rank_overnight_stocks
from .fixtures import stock_context


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
