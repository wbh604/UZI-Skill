"""Account-level allocation for ETF and stock tail candidates."""

from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR
from math import isfinite
from typing import Iterable

from .config import DecisionConfig
from .contracts import Allocation, Candidate


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
    total_budget = Decimal(str(min(config.max_total_exposure, config.account_assets)))
    instrument_cap = Decimal(str(config.max_instrument_exposure))
    remaining = total_budget
    allocations: list[Allocation] = []
    reasons: list[str] = []

    for item in candidates:
        if item.rejections:
            reasons.append(f"skipped_rejected_candidate:{item.instrument_id}")
            continue
        if (
            not isfinite(item.max_buy_price)
            or item.max_buy_price <= 0
            or item.lot_size <= 0
            or not isfinite(item.score)
        ):
            reasons.append(f"skipped_invalid_candidate:{item.instrument_id}")
            continue

        price = Decimal(str(item.max_buy_price))
        lot_size = Decimal(item.lot_size)
        lot_notional = price * lot_size
        budget = min(instrument_cap, remaining)
        lots = (budget / lot_notional).to_integral_value(rounding=ROUND_FLOOR)
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
