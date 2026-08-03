from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pytest

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.contracts import (
    DecisionStatus,
    InstrumentType,
    QuoteSnapshot,
)


def test_quote_snapshot_rejects_non_positive_price():
    with pytest.raises(ValueError, match="last_price must be positive"):
        QuoteSnapshot(
            instrument_id="600406.SH",
            instrument_type=InstrumentType.STOCK,
            timestamp=datetime(
                2026, 8, 3, 14, 10, tzinfo=ZoneInfo("Asia/Shanghai")
            ),
            last_price=0.0,
            open=25.0,
            high=25.1,
            low=24.8,
            pre_close=24.5,
            volume=1000.0,
            amount=25000.0,
            source="fixture",
            fetched_at=datetime(
                2026, 8, 3, 14, 10, tzinfo=ZoneInfo("Asia/Shanghai")
            ),
        )


def test_decision_status_keeps_blocked_distinct_from_no_trade():
    assert DecisionStatus.BLOCKED.value == "blocked"
    assert DecisionStatus.NO_TRADE.value == "no_trade"
    assert DecisionStatus.BLOCKED is not DecisionStatus.NO_TRADE
