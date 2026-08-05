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


def test_allocator_can_buy_stock_above_40_when_one_lot_fits_effective_cap():
    stock = candidate("688318.SH", kind="stock", price=79.50, lot_size=100, score=90)

    allocations, _ = allocate_portfolio(
        [],
        [stock],
        DecisionConfig(account_assets=4_000.0),
    )

    assert len(allocations) == 1
    assert allocations[0].quantity == 100
    assert allocations[0].notional == 7_950.0


def test_allocator_never_exceeds_lower_available_cash_and_selects_one_position():
    etf = candidate("513050.SH", kind="etf", price=1.20, lot_size=100, score=90)
    stock = candidate("600406.SH", kind="stock", price=25.0, lot_size=100, score=89)
    config = DecisionConfig(available_cash_cny=7_600.0)

    allocations, _ = allocate_portfolio([etf], [stock], config)

    assert len(allocations) == 1
    assert allocations[0].notional <= 7_600.0
    assert allocations[0].notional > 7_000.0


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
