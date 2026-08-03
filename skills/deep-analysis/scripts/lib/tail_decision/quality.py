"""Cross-source quality gate for realtime tail-decision quotes."""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from statistics import median
from typing import Iterable

from .config import DecisionConfig
from .contracts import (
    InstrumentType,
    QualityDecision,
    QualityLevel,
    QuoteSnapshot,
)


def evaluate_quote_quality(
    instrument_id: str,
    quotes: Iterable[QuoteSnapshot],
    now: datetime,
    config: DecisionConfig,
) -> QualityDecision:
    deduplicated = _deduplicate_by_source(quotes)
    source_quotes = tuple(sorted(deduplicated.values(), key=lambda item: item.source))
    reasons: list[str] = []

    if not source_quotes:
        return QualityDecision(
            instrument_id=instrument_id,
            level=QualityLevel.BLOCKED,
            reasons=("no_valid_quotes",),
            canonical_quote=None,
            source_quotes=(),
        )

    expected_type = _expected_instrument_type(instrument_id)
    if any(quote.instrument_id != instrument_id for quote in source_quotes):
        reasons.append("mismatched_instrument_id")
    if any(quote.instrument_type is not expected_type for quote in source_quotes):
        reasons.append("mismatched_instrument_type")
    if any(not _has_finite_values(quote) for quote in source_quotes):
        reasons.append("non_finite_quote")

    quote_ages = [
        max(
            (now - quote.timestamp).total_seconds(),
            (now - quote.fetched_at).total_seconds(),
        )
        for quote in source_quotes
    ]
    if max(quote_ages) > config.max_quote_age_seconds:
        reasons.append("stale_quote")

    prices = [quote.last_price for quote in source_quotes]
    median_price = median(prices)
    if isfinite(median_price) and median_price > 0:
        deviation_pct = (max(prices) - min(prices)) / median_price * 100.0
        if deviation_pct > config.max_price_deviation_pct:
            reasons.append("cross_source_price_deviation")
    else:
        reasons.append("non_finite_quote")

    if reasons:
        return QualityDecision(
            instrument_id=instrument_id,
            level=QualityLevel.BLOCKED,
            reasons=tuple(dict.fromkeys(reasons)),
            canonical_quote=None,
            source_quotes=source_quotes,
        )

    canonical = min(
        source_quotes,
        key=lambda quote: (abs(quote.last_price - median_price), quote.source),
    )
    if len(source_quotes) < config.min_sources_for_recommendation:
        return QualityDecision(
            instrument_id=instrument_id,
            level=QualityLevel.DEGRADED,
            reasons=("insufficient_independent_sources",),
            canonical_quote=canonical,
            source_quotes=source_quotes,
        )
    return QualityDecision(
        instrument_id=instrument_id,
        level=QualityLevel.PASS,
        reasons=(),
        canonical_quote=canonical,
        source_quotes=source_quotes,
    )


def _deduplicate_by_source(
    quotes: Iterable[QuoteSnapshot],
) -> dict[str, QuoteSnapshot]:
    deduplicated: dict[str, QuoteSnapshot] = {}
    for quote in quotes:
        current = deduplicated.get(quote.source)
        if current is None or quote.fetched_at > current.fetched_at:
            deduplicated[quote.source] = quote
    return deduplicated


def _expected_instrument_type(instrument_id: str) -> InstrumentType:
    code = instrument_id.split(".", 1)[0]
    if code.startswith(("5", "15", "16")):
        return InstrumentType.ETF
    return InstrumentType.STOCK


def _has_finite_values(quote: QuoteSnapshot) -> bool:
    return all(
        isfinite(value)
        for value in (
            quote.last_price,
            quote.open,
            quote.high,
            quote.low,
            quote.pre_close,
            quote.volume,
            quote.amount,
        )
    )
