"""Deterministic ETF eligibility filters and tail-strength ranking."""

from __future__ import annotations

from math import isfinite
from typing import Iterable

from .config import DecisionConfig
from .contracts import (
    Candidate,
    InstrumentContext,
    InstrumentType,
    QualityLevel,
)


def rank_etfs(
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
    selected = ranked[: config.max_etf_candidates]
    for candidate in ranked[config.max_etf_candidates :]:
        rejected[candidate.instrument_id] = ["below_candidate_cutoff"]
    return selected, rejected


def _eligibility_failures(
    context: InstrumentContext, config: DecisionConfig
) -> list[str]:
    failures: list[str] = []
    if context.instrument_type is not InstrumentType.ETF:
        failures.append("wrong_instrument_type")
    if context.quality.level is not QualityLevel.PASS:
        failures.append("quality_below_pass")
    if context.quote is None:
        failures.append("missing_quote")
    if context.intraday.get("production_ready") is not True:
        failures.append("intraday_not_ready")

    daily_amount = _number(
        context.historical.get(
            "avg_amount_20d", context.historical.get("latest_amount")
        )
    )
    if daily_amount is None or daily_amount < config.min_etf_daily_amount:
        failures.append("low_turnover")

    lot_size = context.metadata.get("lot_size")
    if not isinstance(lot_size, int) or isinstance(lot_size, bool) or lot_size <= 0:
        failures.append("unknown_lot_size")
    tracking = context.metadata.get("tracking_index") or context.metadata.get(
        "tracking_target"
    )
    if not isinstance(tracking, str) or not tracking.strip():
        failures.append("missing_tracking_metadata")

    premium = _number(context.metadata.get("premium_proxy_pct"))
    if premium is None:
        failures.append("missing_premium_proxy")
    elif premium > config.max_etf_premium_pct:
        failures.append("premium_above_limit")
    return failures


def _candidate(context: InstrumentContext, config: DecisionConfig) -> Candidate:
    assert context.quote is not None
    amount = _number(context.historical.get("avg_amount_20d")) or 0.0
    money_flow = _number(context.historical.get("net_mf_amount")) or 0.0
    normalized_flow = _clamp(money_flow / amount if amount > 0 else 0.0, -1.0, 1.0)
    tail_return = _number(context.intraday.get("tail_return_pct")) or 0.0
    vwap_distance = _number(context.intraday.get("vwap_distance_pct")) or 0.0
    range_position = _number(context.intraday.get("range_position"))
    volume_ratio = _number(context.intraday.get("volume_ratio"))

    score = 50.0
    score += tail_return * 30.0
    score += vwap_distance * 20.0
    score += ((range_position if range_position is not None else 0.5) - 0.5) * 10.0
    score += normalized_flow * 10.0
    score += ((volume_ratio if volume_ratio is not None else 1.0) - 1.0) * 10.0

    daily_gain = _number(context.historical.get("daily_gain_pct"))
    if daily_gain is not None and daily_gain > config.etf_excessive_daily_gain_pct:
        score -= (daily_gain - config.etf_excessive_daily_gain_pct) * 5.0
    nav_age = _number(context.metadata.get("nav_age_minutes"))
    if nav_age is None or nav_age > config.etf_nav_stale_minutes:
        score -= 10.0
    if context.metadata.get("underlying_market_open") is False:
        score -= 8.0

    lot_size = int(context.metadata["lot_size"])
    max_buy_price = round(
        context.quote.last_price * (1.0 + config.buy_slippage_bps / 10_000.0),
        4,
    )
    return Candidate(
        instrument_id=context.instrument_id,
        name=context.name,
        instrument_type=InstrumentType.ETF,
        score=round(score, 6),
        max_buy_price=max_buy_price,
        lot_size=lot_size,
        reasons=("quality_pass", "liquidity_pass", "tail_strength_ranked"),
        rejections=(),
        exit_plan={
            "exit_session": "next_trading_day",
            "take_profit_pct": 1.5,
            "stop_loss_pct": -1.0,
            "time_exit": "10:00",
            "cancel_if": (
                "quote_quality_blocked",
                "underlying_market_dislocation",
                "untradeable_open",
            ),
        },
        theme=str(
            context.metadata.get("theme")
            or context.metadata.get("tracking_index")
            or context.metadata["tracking_target"]
        ),
    )


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
