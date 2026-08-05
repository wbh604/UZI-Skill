"""Eligibility filters and deterministic ranking for overnight A-share trades."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Iterable

from .config import DecisionConfig
from .contracts import (
    Candidate,
    InstrumentContext,
    InstrumentType,
    QualityLevel,
)


def rank_overnight_stocks(
    contexts: Iterable[InstrumentContext], config: DecisionConfig
) -> tuple[list[Candidate], dict[str, list[str]]]:
    ranked: list[Candidate] = []
    rejected: dict[str, list[str]] = {}
    for context in contexts:
        failures = _eligibility_failures(context, config)
        if failures:
            rejected[context.instrument_id] = failures
            continue
        ranked.append(_candidate(context, config))

    ranked.sort(key=lambda item: (-item.score, item.instrument_id))
    selected = ranked[: config.max_stock_candidates]
    for candidate in ranked[config.max_stock_candidates :]:
        rejected[candidate.instrument_id] = ["below_candidate_cutoff"]
    return selected, rejected


def _eligibility_failures(
    context: InstrumentContext, config: DecisionConfig
) -> list[str]:
    failures: list[str] = []
    if context.instrument_type is not InstrumentType.STOCK:
        failures.append("wrong_instrument_type")
    if context.quality.level is not QualityLevel.PASS:
        failures.append("quality_below_pass")
    if context.quote is None:
        failures.append("missing_quote")
        return failures
    if context.intraday.get("production_ready") is not True:
        failures.append("intraday_not_ready")
    if _uzi_state(context) == "blocked":
        failures.append("uzi_review_blocked")

    upper_name = context.name.upper()
    if (
        context.metadata.get("is_st") is True
        or context.metadata.get("delisting") is True
        or upper_name.startswith(("ST", "*ST"))
        or "退" in context.name
    ):
        failures.append("st_or_delisting")
    if context.metadata.get("suspended") is True:
        failures.append("suspended")

    listing_days = _number(context.metadata.get("listing_days"))
    if listing_days is None:
        failures.append("unknown_listing_age")
    elif listing_days < config.min_stock_listing_days:
        failures.append("listing_too_recent")

    amount = _number(context.historical.get("avg_amount_20d"))
    if amount is None or amount < config.min_stock_daily_amount:
        failures.append("low_turnover")

    instrument_cap = config.effective_position_cap_cny
    if instrument_cap is None:
        instrument_cap = config.configured_position_cap_cny
    lot_size = context.metadata.get("lot_size", config.stock_lot_size)
    if (
        not isinstance(lot_size, int)
        or isinstance(lot_size, bool)
        or lot_size <= 0
        or context.quote.last_price * lot_size > instrument_cap
    ):
        failures.append("minimum_lot_exceeds_cap")

    daily_gain = _number(context.historical.get("daily_gain_pct"))
    if daily_gain is None and context.quote.pre_close > 0:
        daily_gain = (
            context.quote.last_price / context.quote.pre_close - 1.0
        ) * 100.0
    if daily_gain is not None and daily_gain >= config.max_stock_daily_gain_pct:
        failures.append("daily_gain_too_high")

    limit_up = _number(context.metadata.get("limit_up"))
    if limit_up is not None and limit_up > 0:
        distance_pct = (limit_up - context.quote.last_price) / limit_up * 100.0
        if distance_pct <= config.near_limit_distance_pct:
            failures.append("near_unbuyable_limit")

    if any(
        context.events.get(key) is True
        for key in (
            "adverse_event",
            "major_negative",
            "reduction_risk",
            "next_day_event_risk",
        )
    ):
        failures.append("adverse_event_risk")
    return failures


def _candidate(context: InstrumentContext, config: DecisionConfig) -> Candidate:
    assert context.quote is not None
    amount = _number(context.historical.get("avg_amount_20d")) or 0.0
    latest_flow = _number(context.historical.get("net_mf_amount")) or 0.0
    five_day_flow = _number(context.historical.get("net_mf_amount_5d")) or 0.0
    tail_return = _number(context.intraday.get("tail_return_pct")) or 0.0
    vwap_distance = _number(context.intraday.get("vwap_distance_pct")) or 0.0
    range_position = _number(context.intraday.get("range_position"))
    amount_ratio = _number(context.intraday.get("amount_ratio"))
    sector_strength = _number(
        context.historical.get("sector_relative_strength")
    ) or 0.0
    volatility = _number(context.historical.get("volatility_20d_pct")) or 0.0
    return_20d = _number(context.historical.get("return_20d_pct")) or 0.0

    score = 50.0
    score += tail_return * 25.0
    score += vwap_distance * 15.0
    score += ((range_position if range_position is not None else 0.5) - 0.5) * 10.0
    score += ((amount_ratio if amount_ratio is not None else 1.0) - 1.0) * 8.0
    score += _clamp(latest_flow / amount if amount else 0.0, -1.0, 1.0) * 10.0
    score += _clamp(five_day_flow / amount if amount else 0.0, -2.0, 2.0) * 5.0
    score += sector_strength * 8.0
    score -= max(0.0, volatility - 3.0) * 3.0
    score -= max(0.0, return_20d - 15.0) * 0.8

    lot_size = int(context.metadata.get("lot_size", config.stock_lot_size))
    max_buy_price = round(
        context.quote.last_price * (1.0 + config.buy_slippage_bps / 10_000.0),
        2,
    )
    return Candidate(
        instrument_id=context.instrument_id,
        name=context.name,
        instrument_type=InstrumentType.STOCK,
        score=round(score, 6),
        max_buy_price=max_buy_price,
        lot_size=lot_size,
        reasons=(
            "quality_pass",
            "tradability_pass",
            "overnight_strength_ranked",
            *_research_audit_reasons(context),
        ),
        rejections=(),
        exit_plan={
            "exit_session": "next_trading_day",
            "t_plus_one_required": True,
            "take_profit_pct": 2.0,
            "stop_loss_pct": -1.5,
            "time_exit": "10:00",
            "cancel_if": (
                "quote_quality_blocked",
                "adverse_event_detected",
                "untradeable_open",
            ),
        },
        theme=str(
            context.metadata.get("theme")
            or context.metadata.get("sector")
            or context.instrument_id
        ),
    )


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _uzi_state(context: InstrumentContext) -> str | None:
    evidence = context.metadata.get("research_evidence")
    if not isinstance(evidence, Mapping):
        return None
    state = evidence.get("uzi_state")
    return state if state in ("approved", "blocked") else None


def _research_audit_reasons(context: InstrumentContext) -> tuple[str, ...]:
    evidence = context.metadata.get("research_evidence")
    if not isinstance(evidence, Mapping):
        return ("uzi_unavailable",)

    reasons: list[str] = []
    ai_score = _bounded_number(evidence.get("ai_score"), 0.0, 100.0)
    if ai_score is not None:
        reasons.append(f"ai_discovery_score:{ai_score:.1f}")
    uzi_score = _bounded_number(evidence.get("uzi_score"), 0.0, 100.0)
    coverage = _bounded_number(evidence.get("uzi_coverage"), 0.0, 1.0)
    if uzi_score is not None:
        reasons.append(f"uzi_score:{uzi_score:.1f}")
    if coverage is not None:
        reasons.append(f"uzi_coverage:{coverage:.2f}")
    if _uzi_state(context) is None or uzi_score is None or coverage is None:
        reasons.append("uzi_unavailable")
    reasons.extend(f"evidence_date:{value}" for value in _audit_strings(evidence.get("source_dates")))
    reasons.extend(f"evidence_reason:{value}" for value in _audit_strings(evidence.get("reasons")))
    return tuple(reasons)


def _bounded_number(value: object, minimum: float, maximum: float) -> float | None:
    number = _number(value)
    return number if number is not None and minimum <= number <= maximum else None


def _audit_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(
        item for item in value
        if isinstance(item, str) and item.strip()
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
