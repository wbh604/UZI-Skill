"""Money-flow history normalization. Provider observations remain separate."""
from __future__ import annotations

from datetime import date, datetime
from math import isfinite

MAIN_NET = "主力净流入-净额"


def net_amount(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def trading_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) == 10:
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return None


def recent_history(rows, *, date_key: str, amount_key: str, through: date, limit: int = 20) -> list[dict]:
    """Return newest-first. Retain incomplete dates so totals do not skip gaps."""
    by_date = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = trading_date(row.get(date_key))
        if day is None or day > through or day.weekday() >= 5:
            continue
        value = net_amount(row.get(amount_key))
        prior = by_date.get(day)
        if prior is not None and prior[amount_key] != value:
            value = None
        by_date[day] = {**row, date_key: day.isoformat(), amount_key: value}
    return [by_date[day] for day in sorted(by_date, reverse=True)[:limit]]


def recent_main_history(rows, limit: int = 20) -> list:
    if not isinstance(rows, list) or not rows:
        return []
    # New and old caches from AkShare may differ in row order.
    days = [trading_date(row.get("日期")) if isinstance(row, dict) else None for row in rows]
    if all(day is not None for day in days):
        return recent_history(rows, date_key="日期", amount_key=MAIN_NET, through=max(days), limit=limit)
    return rows[:limit]


def window_net(rows, count: int, amount_key: str = MAIN_NET) -> float | None:
    if not isinstance(rows, list) or len(rows) < count:
        return None
    window = recent_main_history(rows, count) if amount_key == MAIN_NET else rows[:count]
    if len(window) != count or not all(isinstance(row, dict) for row in window):
        return None
    values = [net_amount(row.get(amount_key)) for row in window]
    return net_amount(sum(values)) if all(value is not None for value in values) else None
