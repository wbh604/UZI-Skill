"""Shared fixtures for tail-decision tests."""

from datetime import datetime
from zoneinfo import ZoneInfo

from lib.tail_decision.contracts import (
    Allocation,
    Candidate,
    DecisionRun,
    DecisionStatus,
    InstrumentContext,
    InstrumentType,
    QualityDecision,
    QualityLevel,
    QuoteSnapshot,
)


def candidate(
    instrument_id: str,
    *,
    kind: str,
    price: float,
    lot_size: int,
    score: float,
    theme: str | None = None,
) -> Candidate:
    instrument_type = InstrumentType(kind)
    return Candidate(
        instrument_id=instrument_id,
        name=f"{kind}-{instrument_id}",
        instrument_type=instrument_type,
        score=float(score),
        max_buy_price=float(price),
        lot_size=lot_size,
        reasons=("fixture",),
        rejections=(),
        exit_plan={"exit_session": "next_trading_day"},
        theme=theme or instrument_id,
    )


def allocation(
    instrument_id: str,
    *,
    quantity: int,
    limit_price: float,
    score: float = 80.0,
) -> Allocation:
    return Allocation(
        instrument_id=instrument_id,
        quantity=quantity,
        limit_price=limit_price,
        notional=quantity * limit_price,
        candidate_score=score,
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


def stock_context(
    instrument_id: str,
    *,
    price: float,
    name: str,
    tail_return_pct: float = 0.6,
    is_st: bool = False,
    pre_close: float | None = None,
    limit_up: float | None = None,
    suspended: bool = False,
    listing_days: int = 365,
    amount: float = 500_000_000.0,
    adverse_event: bool = False,
) -> InstrumentContext:
    previous = pre_close if pre_close is not None else price / 1.01
    first = quote(
        instrument_id=instrument_id,
        instrument_type=InstrumentType.STOCK,
        last_price=price,
        open=previous,
        high=max(price, previous),
        low=min(price, previous),
        pre_close=previous,
        source="eastmoney",
    )
    second = quote(
        instrument_id=instrument_id,
        instrument_type=InstrumentType.STOCK,
        last_price=price,
        open=previous,
        high=max(price, previous),
        low=min(price, previous),
        pre_close=previous,
        source="tencent",
    )
    quality_decision = QualityDecision(
        instrument_id=instrument_id,
        level=QualityLevel.PASS,
        reasons=(),
        canonical_quote=first,
        source_quotes=(first, second),
    )
    return InstrumentContext(
        instrument_id=instrument_id,
        name=name,
        instrument_type=InstrumentType.STOCK,
        quality=quality_decision,
        quote=first,
        historical={
            "avg_amount_20d": amount,
            "daily_gain_pct": (price / previous - 1.0) * 100.0,
            "return_20d_pct": 4.0,
            "volatility_20d_pct": 1.5,
            "net_mf_amount": amount * 0.02,
            "net_mf_amount_5d": amount * 0.05,
            "sector_relative_strength": 0.5,
        },
        intraday={
            "production_ready": True,
            "tail_return_pct": tail_return_pct,
            "vwap_distance_pct": 0.2,
            "range_position": 0.7,
            "amount_ratio": 1.2,
        },
        events={"adverse_event": adverse_event},
        metadata={
            "lot_size": 100,
            "is_st": is_st,
            "delisting": False,
            "suspended": suspended,
            "listing_days": listing_days,
            "limit_up": limit_up,
            "theme": "fixture-sector",
        },
    )


def decision_run(*, run_id: str) -> DecisionRun:
    etf = candidate("513050.SH", kind="etf", price=1.18, lot_size=100, score=80)
    stock = candidate("600406.SH", kind="stock", price=25.0, lot_size=100, score=78)
    return DecisionRun(
        run_id=run_id,
        as_of=datetime(2026, 8, 3, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        status=DecisionStatus.RECOMMENDED,
        quality=(),
        etf_candidates=(etf,),
        stock_candidates=(stock,),
        allocations=(
            Allocation(
                instrument_id="513050.SH",
                quantity=3_300,
                limit_price=1.18,
                notional=3_894.0,
                candidate_score=80.0,
            ),
            Allocation(
                instrument_id="600406.SH",
                quantity=100,
                limit_price=25.0,
                notional=2_500.0,
                candidate_score=78.0,
            ),
        ),
        reasons=("dual_source_quotes_passed",),
        strategy_version="tail-v1",
        config_hash="fixture-config-hash",
    )
