from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.portfolio import allocate_portfolio
from .fixtures import candidate


def test_allocator_selects_only_the_best_candidate_across_etf_and_stock():
    etf = candidate("513050.SH", kind="etf", price=1.18, lot_size=100, score=80)
    stock = candidate("600406.SH", kind="stock", price=25.0, lot_size=100, score=78)

    allocations, reasons = allocate_portfolio([etf], [stock], DecisionConfig())

    assert sum(item.notional for item in allocations) <= 12_000.0
    assert all(item.notional <= 12_000.0 for item in allocations)
    assert [item.instrument_id for item in allocations] == ["513050.SH"]


def test_allocator_can_select_stock_when_it_has_the_higher_score():
    etf = candidate("513050.SH", kind="etf", price=1.18, lot_size=100, score=80)
    stock = candidate("600406.SH", kind="stock", price=25.0, lot_size=100, score=82)

    allocations, reasons = allocate_portfolio([etf], [stock], DecisionConfig())

    assert [item.instrument_id for item in allocations] == ["600406.SH"]


def test_allocator_skips_unaffordable_top_candidate_and_selects_next_best():
    expensive = candidate(
        "600519.SH", kind="stock", price=1600.0, lot_size=100, score=99
    )
    etf = candidate("513050.SH", kind="etf", price=1.18, lot_size=100, score=80)

    allocations, reasons = allocate_portfolio([etf], [expensive], DecisionConfig())

    assert [item.instrument_id for item in allocations] == ["513050.SH"]
    assert "skipped_unaffordable:600519.SH" in reasons


def test_allocator_returns_empty_when_no_lot_fits():
    stock = candidate("600519.SH", kind="stock", price=1600.0, lot_size=100, score=99)

    allocations, reasons = allocate_portfolio([], [stock], DecisionConfig())

    assert allocations == []
    assert "no_affordable_candidate" in reasons


def test_allocator_fails_closed_when_available_cash_is_missing():
    stock = candidate("600406.SH", kind="stock", price=25.0, lot_size=100, score=82)

    allocations, reasons = allocate_portfolio(
        [], [stock], DecisionConfig(available_cash_cny=None)
    )

    assert allocations == []
    assert "available_cash_missing" in reasons
