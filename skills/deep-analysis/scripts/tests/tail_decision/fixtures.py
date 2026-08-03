"""Shared fixtures for tail-decision tests."""

from datetime import datetime
from zoneinfo import ZoneInfo

from lib.tail_decision.contracts import InstrumentType, QuoteSnapshot


def quote(**overrides) -> QuoteSnapshot:
    now = datetime(2026, 8, 3, 14, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    values = {
        "instrument_id": "600406.SH",
        "instrument_type": InstrumentType.STOCK,
        "timestamp": now,
        "last_price": 25.0,
        "open": 24.8,
        "high": 25.1,
        "low": 24.7,
        "pre_close": 24.5,
        "volume": 100_000.0,
        "amount": 2_500_000.0,
        "source": "fixture",
        "fetched_at": now,
    }
    values.update(overrides)
    return QuoteSnapshot(**values)
