"""Account-level allocation for ETF and stock tail candidates."""

from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR
from math import isfinite
from numbers import Integral, Real
from typing import Iterable

from .config import DecisionConfig
from .contracts import Allocation, Candidate


def _is_finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, Real)
        and isfinite(value)
    )


def allocate_portfolio(
    etfs: Iterable[Candidate],
    stocks: Iterable[Candidate],
    config: DecisionConfig,
) -> tuple[list[Allocation], list[str]]:
    """Allocate the single best feasible ETF or stock under shared cash caps."""

    candidates = sorted(
        [*etfs, *stocks],
        key=lambda item: (-item.score, item.instrument_id),
    )
    allocations: list[Allocation] = []
    reasons: list[str] = []
    effective_cap = config.effective_position_cap_cny
    if effective_cap is None:
        return allocations, ["available_cash_missing"]

    remaining = Decimal(str(effective_cap))

    for item in candidates:
        if item.rejections:
            reasons.append(f"skipped_rejected_candidate:{item.instrument_id}")
            continue
        if (
            not _is_finite_number(item.max_buy_price)
            or item.max_buy_price <= 0
            or isinstance(item.lot_size, bool)
            or not isinstance(item.lot_size, Integral)
            or item.lot_size <= 0
            or not _is_finite_number(item.score)
        ):
            reasons.append(f"skipped_invalid_candidate:{item.instrument_id}")
            continue

        price = Decimal(str(item.max_buy_price))
        lot_size = Decimal(item.lot_size)
        lot_notional = price * lot_size
        lots = (remaining / lot_notional).to_integral_value(rounding=ROUND_FLOOR)
        if lots < 1:
            reasons.append(f"skipped_unaffordable:{item.instrument_id}")
            continue

        quantity = int(lots * lot_size)
        notional = price * Decimal(quantity)
        allocations.append(
            Allocation(
                instrument_id=item.instrument_id,
                quantity=quantity,
                limit_price=item.max_buy_price,
                notional=float(notional),
                candidate_score=item.score,
            )
        )
        remaining -= notional
        reasons.append(f"selected_best_candidate:{item.instrument_id}")
        break

    if not allocations:
        reasons.append("no_affordable_candidate")

    return allocations, reasons
