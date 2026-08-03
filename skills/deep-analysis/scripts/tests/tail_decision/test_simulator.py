from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.simulator import (
    simulate_entry,
    simulate_next_session_exit,
    simulate_round_trip,
    summarize_ledger,
)
from .fixtures import allocation


def test_stock_round_trip_applies_minimum_commission_and_sell_tax():
    trade = simulate_round_trip(
        allocation("600406.SH", quantity=100, limit_price=25.0),
        entry_price=25.0,
        exit_price=25.5,
        instrument_type="stock",
        config=DecisionConfig(),
    )

    assert trade["entry_fee"] >= 5.0
    assert trade["exit_fee"] >= 5.0
    assert trade["sell_stamp_tax"] > 0
    assert 0 < trade["net_pnl"] < 50.0


def test_stock_exit_on_entry_date_remains_unfilled():
    item = allocation("600406.SH", quantity=100, limit_price=25.0)
    entry = simulate_entry(
        item,
        bar={
            "timestamp": "2026-08-03T14:30:00+08:00",
            "price": 24.90,
            "volume": 10_000,
        },
        instrument_type="stock",
        config=DecisionConfig(),
    )

    exit_result = simulate_next_session_exit(
        entry,
        bar={
            "timestamp": "2026-08-03T14:40:00+08:00",
            "price": 25.10,
            "volume": 10_000,
        },
        instrument_type="stock",
        config=DecisionConfig(),
    )

    assert entry["filled"] is True
    assert exit_result == {"filled": False, "reason": "stock_t_plus_one"}


@pytest.mark.parametrize(
    ("bar_overrides", "expected_reason"),
    [
        ({"volume": 0}, "zero_volume"),
        ({"suspended": True}, "suspended"),
        ({"limit_up": True}, "limit_up_buy"),
        ({"price": 25.0}, "above_limit_price"),
    ],
)
def test_entry_rejects_non_tradable_or_above_limit_bars(
    bar_overrides,
    expected_reason,
):
    bar = {
        "timestamp": "2026-08-03T14:30:00+08:00",
        "price": 24.90,
        "volume": 10_000,
        **bar_overrides,
    }

    result = simulate_entry(
        allocation("600406.SH", quantity=100, limit_price=25.0),
        bar=bar,
        instrument_type="stock",
        config=DecisionConfig(),
    )

    assert result == {"filled": False, "reason": expected_reason}


def test_exit_rejects_limit_down_bar_on_next_session():
    item = allocation("600406.SH", quantity=100, limit_price=25.0)
    entry = simulate_entry(
        item,
        bar={
            "timestamp": "2026-08-03T14:30:00+08:00",
            "price": 24.90,
            "volume": 10_000,
        },
        instrument_type="stock",
        config=DecisionConfig(),
    )

    result = simulate_next_session_exit(
        entry,
        bar={
            "timestamp": "2026-08-04T09:35:00+08:00",
            "price": 24.00,
            "volume": 10_000,
            "limit_down": True,
        },
        instrument_type="stock",
        config=DecisionConfig(),
    )

    assert result == {"filled": False, "reason": "limit_down_sell"}


def test_ledger_summary_reports_cost_adjusted_metrics_by_type():
    summary = summarize_ledger(
        [
            {
                "filled": True,
                "instrument_type": "stock",
                "entry_notional": 1_000.0,
                "net_pnl": 100.0,
            },
            {
                "filled": True,
                "instrument_type": "etf",
                "entry_notional": 1_000.0,
                "net_pnl": -40.0,
            },
        ]
    )

    assert summary["net_pnl"] == 60.0
    assert summary["net_return_pct"] == 3.0
    assert summary["profit_factor"] == 2.5
    assert summary["maximum_drawdown"] == 40.0
    assert summary["trade_count"] == 2
    assert summary["win_rate_pct"] == 50.0
    assert summary["average_win"] == 100.0
    assert summary["average_loss"] == -40.0
    assert summary["by_instrument_type"]["stock"]["trade_count"] == 1
    assert summary["by_instrument_type"]["etf"]["trade_count"] == 1
