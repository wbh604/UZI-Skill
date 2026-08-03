"""Conservative forward fills and cost-adjusted ledger metrics."""

from __future__ import annotations

from datetime import date, datetime
from math import isfinite
from typing import Any, Iterable, Mapping

from .config import DecisionConfig
from .contracts import Allocation, InstrumentType


def simulate_round_trip(
    allocation: Allocation,
    *,
    entry_price: float,
    exit_price: float,
    instrument_type: str | InstrumentType,
    config: DecisionConfig,
) -> dict[str, Any]:
    """Price a filled round trip with configured slippage, fees, and tax."""

    kind = _instrument_type(instrument_type)
    _require_price(entry_price, "entry_price")
    _require_price(exit_price, "exit_price")
    if allocation.quantity <= 0:
        raise ValueError("allocation quantity must be positive")

    filled_entry = entry_price * (1.0 + config.buy_slippage_bps / 10_000.0)
    filled_exit = exit_price * (1.0 - config.sell_slippage_bps / 10_000.0)
    entry_notional = filled_entry * allocation.quantity
    exit_notional = filled_exit * allocation.quantity
    entry_fee = _commission(entry_notional, kind, config)
    exit_fee = _commission(exit_notional, kind, config)
    stamp_tax = (
        exit_notional * config.stock_sell_stamp_tax_rate
        if kind is InstrumentType.STOCK
        else 0.0
    )
    gross_pnl = exit_notional - entry_notional
    net_pnl = gross_pnl - entry_fee - exit_fee - stamp_tax

    return {
        "filled": True,
        "instrument_id": allocation.instrument_id,
        "instrument_type": kind.value,
        "quantity": allocation.quantity,
        "entry_price": _rounded(filled_entry),
        "exit_price": _rounded(filled_exit),
        "entry_notional": _rounded(entry_notional),
        "exit_notional": _rounded(exit_notional),
        "entry_fee": _rounded(entry_fee),
        "exit_fee": _rounded(exit_fee),
        "sell_stamp_tax": _rounded(stamp_tax),
        "gross_pnl": _rounded(gross_pnl),
        "net_pnl": _rounded(net_pnl),
        "net_return_pct": _rounded(net_pnl / entry_notional * 100.0),
    }


def simulate_entry(
    allocation: Allocation,
    *,
    bar: Mapping[str, Any],
    instrument_type: str | InstrumentType,
    config: DecisionConfig,
) -> dict[str, Any]:
    """Attempt a conservative buy fill against one saved minute bar."""

    kind = _instrument_type(instrument_type)
    price = _bar_price(bar)
    reason = _bar_block_reason(bar, price=price, side="buy")
    if reason:
        return {"filled": False, "reason": reason}

    filled_price = price * (1.0 + config.buy_slippage_bps / 10_000.0)
    if filled_price > allocation.limit_price:
        return {"filled": False, "reason": "above_limit_price"}

    notional = filled_price * allocation.quantity
    return {
        "filled": True,
        "instrument_id": allocation.instrument_id,
        "instrument_type": kind.value,
        "quantity": allocation.quantity,
        "entry_date": _bar_date(bar).isoformat(),
        "entry_price": _rounded(filled_price),
        "entry_notional": _rounded(notional),
        "entry_fee": _rounded(_commission(notional, kind, config)),
    }


def simulate_next_session_exit(
    entry: Mapping[str, Any],
    *,
    bar: Mapping[str, Any],
    instrument_type: str | InstrumentType,
    config: DecisionConfig,
) -> dict[str, Any]:
    """Attempt an exit, enforcing stock T+1 and non-tradable bar rules."""

    if not entry.get("filled"):
        return {"filled": False, "reason": "entry_unfilled"}
    kind = _instrument_type(instrument_type)
    exit_date = _bar_date(bar)
    entry_date = date.fromisoformat(str(entry["entry_date"]))
    if kind is InstrumentType.STOCK and exit_date <= entry_date:
        return {"filled": False, "reason": "stock_t_plus_one"}

    price = _bar_price(bar)
    reason = _bar_block_reason(bar, price=price, side="sell")
    if reason:
        return {"filled": False, "reason": reason}

    filled_price = price * (1.0 - config.sell_slippage_bps / 10_000.0)
    quantity = int(entry["quantity"])
    exit_notional = filled_price * quantity
    entry_notional = float(entry["entry_notional"])
    entry_fee = float(entry["entry_fee"])
    exit_fee = _commission(exit_notional, kind, config)
    stamp_tax = (
        exit_notional * config.stock_sell_stamp_tax_rate
        if kind is InstrumentType.STOCK
        else 0.0
    )
    gross_pnl = exit_notional - entry_notional
    net_pnl = gross_pnl - entry_fee - exit_fee - stamp_tax
    return {
        **dict(entry),
        "filled": True,
        "exit_date": exit_date.isoformat(),
        "exit_price": _rounded(filled_price),
        "exit_notional": _rounded(exit_notional),
        "exit_fee": _rounded(exit_fee),
        "sell_stamp_tax": _rounded(stamp_tax),
        "gross_pnl": _rounded(gross_pnl),
        "net_pnl": _rounded(net_pnl),
        "net_return_pct": _rounded(net_pnl / entry_notional * 100.0),
    }


def summarize_ledger(trades: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize filled trades overall and separately for ETF and stock."""

    filled = [dict(trade) for trade in trades if trade.get("filled")]
    result = _ledger_metrics(filled)
    result["by_instrument_type"] = {
        kind.value: _ledger_metrics(
            [trade for trade in filled if trade.get("instrument_type") == kind.value]
        )
        for kind in (InstrumentType.ETF, InstrumentType.STOCK)
    }
    return result


def _ledger_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    pnls = [float(trade["net_pnl"]) for trade in trades]
    exposure = sum(float(trade["entry_notional"]) for trade in trades)
    net_pnl = sum(pnls)
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    cumulative = 0.0
    peak = 0.0
    maximum_drawdown = 0.0
    for pnl in pnls:
        cumulative += pnl
        peak = max(peak, cumulative)
        maximum_drawdown = max(maximum_drawdown, peak - cumulative)

    if gross_loss:
        profit_factor = gross_profit / gross_loss
    elif gross_profit:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0
    count = len(pnls)
    return {
        "net_pnl": _rounded(net_pnl),
        "net_return_pct": _rounded(net_pnl / exposure * 100.0) if exposure else 0.0,
        "profit_factor": _rounded(profit_factor),
        "maximum_drawdown": _rounded(maximum_drawdown),
        "trade_count": count,
        "win_rate_pct": _rounded(len(wins) / count * 100.0) if count else 0.0,
        "average_win": _rounded(sum(wins) / len(wins)) if wins else 0.0,
        "average_loss": _rounded(sum(losses) / len(losses)) if losses else 0.0,
    }


def _bar_price(bar: Mapping[str, Any]) -> float:
    for key in ("price", "last_price", "close"):
        if key in bar:
            price = float(bar[key])
            _require_price(price, key)
            return price
    raise ValueError("bar must contain price, last_price, or close")


def _bar_date(bar: Mapping[str, Any]) -> date:
    value = bar.get("timestamp", bar.get("date"))
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return date.fromisoformat(value)
    raise ValueError("bar must contain a date or timestamp")


def _bar_block_reason(
    bar: Mapping[str, Any],
    *,
    price: float,
    side: str,
) -> str | None:
    if bool(bar.get("suspended")):
        return "suspended"
    if float(bar.get("volume", 0.0)) <= 0:
        return "zero_volume"
    if side == "buy" and _at_price_limit(bar.get("limit_up"), price, upper=True):
        return "limit_up_buy"
    if side == "sell" and _at_price_limit(bar.get("limit_down"), price, upper=False):
        return "limit_down_sell"
    return None


def _at_price_limit(value: Any, price: float, *, upper: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    boundary = float(value)
    return price >= boundary if upper else price <= boundary


def _commission(
    notional: float,
    kind: InstrumentType,
    config: DecisionConfig,
) -> float:
    rate = (
        config.stock_commission_rate
        if kind is InstrumentType.STOCK
        else config.etf_commission_rate
    )
    return max(config.minimum_commission, notional * rate)


def _instrument_type(value: str | InstrumentType) -> InstrumentType:
    return value if isinstance(value, InstrumentType) else InstrumentType(value)


def _require_price(value: float, field_name: str) -> None:
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _rounded(value: float) -> float:
    return round(value, 6)
