"""Normalize price bars before computing technical indicators or caching them."""
from __future__ import annotations

import math

_PRICES = {
    "开盘": ("开盘", "Open", "open"),
    "收盘": ("收盘", "Close", "close"),
    "最高": ("最高", "High", "high"),
    "最低": ("最低", "Low", "low"),
}


def _number(row: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, bool):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(number):
            return number
    return None


def clean_kline_rows(rows, *, require_open: bool = True) -> list[dict]:
    """Keep complete, finite price rows; missing volume is not a zero trade."""
    if not isinstance(rows, list):
        return []
    clean = []
    for row in rows:
        if not isinstance(row, dict) or "_kline_fetch_error" in row:
            continue
        prices = {key: _number(row, aliases) for key, aliases in _PRICES.items()
                  if require_open or key != "开盘"}
        if any(value is None or value <= 0 for value in prices.values()):
            continue
        if not all(prices["最低"] <= value <= prices["最高"] for value in prices.values()):
            continue
        data = {key: (None if isinstance(value, float) and not math.isfinite(value) else value)
                for key, value in row.items()}
        data.update(prices)
        volume = _number(row, ("成交量", "Volume", "volume"))
        data["成交量"] = volume if volume is not None and volume >= 0 else None
        clean.append(data)
    return clean


def usable_kline_snapshot(data) -> bool:
    """Reject previously computed technical snapshots with invalid values."""
    if not isinstance(data, dict):
        return False
    count = data.get("kline_count")
    if type(count) is not int or count <= 0:
        return False
    candles = data.get("candles_60d")
    if candles is not None and (not isinstance(candles, list) or not candles
                                or len(clean_kline_rows(candles)) != len(candles)):
        return False

    def finite(value):
        if isinstance(value, float):
            return math.isfinite(value)
        if isinstance(value, str):
            return value.strip().lower().rstrip("%") not in {
                "nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"
            }
        if isinstance(value, dict):
            return all(finite(item) for item in value.values())
        if isinstance(value, list):
            return all(finite(item) for item in value)
        return True

    return all(finite(data.get(field)) for field in ("indicators", "kline_stats", "ma20_60d", "ma60_60d", "close_60d"))
