"""Shared fixtures for tail-decision tests."""

from datetime import datetime
from zoneinfo import ZoneInfo

from lib.tail_decision.contracts import (
    InstrumentContext,
    InstrumentType,
    QualityDecision,
    QualityLevel,
    QuoteSnapshot,
)


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


def etf_context(
    instrument_id: str,
    *,
    amount: float,
    tail_return_pct: float,
    vwap_distance_pct: float,
    quality: str,
) -> InstrumentContext:
    first = quote(
        instrument_id=instrument_id,
        instrument_type=InstrumentType.ETF,
        last_price=1.18,
        open=1.17,
        high=1.19,
        low=1.16,
        pre_close=1.16,
        source="eastmoney",
    )
    second = quote(
        instrument_id=instrument_id,
        instrument_type=InstrumentType.ETF,
        last_price=1.18,
        open=1.17,
        high=1.19,
        low=1.16,
        pre_close=1.16,
        source="tencent",
    )
    level = QualityLevel(quality)
    quality_decision = QualityDecision(
        instrument_id=instrument_id,
        level=level,
        reasons=(),
        canonical_quote=first,
        source_quotes=(first, second),
    )
    return InstrumentContext(
        instrument_id=instrument_id,
        name=f"ETF-{instrument_id}",
        instrument_type=InstrumentType.ETF,
        quality=quality_decision,
        quote=first,
        historical={
            "avg_amount_20d": amount,
            "latest_amount": amount,
            "return_5d_pct": 1.0,
            "net_mf_amount": amount * 0.02,
            "daily_gain_pct": 1.0,
        },
        intraday={
            "production_ready": True,
            "tail_return_pct": tail_return_pct,
            "vwap_distance_pct": vwap_distance_pct,
            "range_position": 0.8,
            "volume_ratio": 1.2,
        },
        events={},
        metadata={
            "lot_size": 100,
            "tracking_index": "fixture-index",
            "premium_proxy_pct": 0.0,
            "nav_age_minutes": 1,
            "underlying_market_open": True,
            "theme": instrument_id,
        },
    )
