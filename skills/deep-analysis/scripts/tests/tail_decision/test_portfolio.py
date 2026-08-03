from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.portfolio import allocate_portfolio
from .fixtures import candidate


def test_etf_and_stock_share_one_8000_cap():
    etf = candidate("513050.SH", kind="etf", price=1.18, lot_size=100, score=80)
    stock = candidate("600406.SH", kind="stock", price=25.0, lot_size=100, score=78)

    allocations, reasons = allocate_portfolio([etf], [stock], DecisionConfig())

    assert sum(item.notional for item in allocations) <= 8_000.0
    assert all(item.notional <= 4_000.0 for item in allocations)
    assert {item.instrument_id for item in allocations} == {"513050.SH", "600406.SH"}


def test_allocator_returns_empty_when_no_lot_fits():
    stock = candidate("600519.SH", kind="stock", price=1600.0, lot_size=100, score=99)

    allocations, reasons = allocate_portfolio([], [stock], DecisionConfig())

    assert allocations == []
    assert "no_affordable_candidate" in reasons
