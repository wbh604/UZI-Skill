"""Pure, deterministic historical and intraday feature builders."""

from __future__ import annotations

from datetime import datetime, time
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


SHANGHAI = ZoneInfo("Asia/Shanghai")


def build_intraday_features(bars: pd.DataFrame, as_of: datetime) -> dict[str, Any]:
    result = _empty_intraday_features()
    required = {"timestamp", "close", "volume", "amount"}
    if bars.empty or not required.issubset(bars.columns):
        return result

    cutoff = _shanghai_timestamp(as_of)
    frame = bars.copy()
    frame["timestamp"] = frame["timestamp"].map(_shanghai_timestamp_or_nat)
    frame = frame.dropna(subset=["timestamp"])
    frame = frame[
        (frame["timestamp"] <= cutoff)
        & (frame["timestamp"].map(lambda value: value.date()) == cutoff.date())
    ].sort_values("timestamp", kind="stable")
    if frame.empty:
        return result

    for column in ("close", "volume", "amount"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["close", "volume", "amount"])
    if frame.empty:
        return result

    latest = frame.iloc[-1]
    tail_start = cutoff.replace(hour=14, minute=10, second=0, microsecond=0)
    baseline_cutoff = cutoff.replace(hour=14, minute=0, second=0, microsecond=0)
    production_ready = bool((frame["timestamp"] >= tail_start).any())
    baseline_rows = frame[frame["timestamp"] <= baseline_cutoff]

    cumulative_volume = float(frame["volume"].sum())
    cumulative_amount = float(frame["amount"].sum())
    vwap = (
        cumulative_amount / cumulative_volume if cumulative_volume > 0 else None
    )
    last_price = float(latest["close"])
    tail_return = None
    if production_ready and not baseline_rows.empty:
        baseline_price = float(baseline_rows.iloc[-1]["close"])
        if baseline_price > 0:
            tail_return = (last_price / baseline_price - 1.0) * 100.0

    high_values = pd.to_numeric(
        frame["high"] if "high" in frame.columns else frame["close"],
        errors="coerce",
    )
    low_values = pd.to_numeric(
        frame["low"] if "low" in frame.columns else frame["close"],
        errors="coerce",
    )
    session_high = float(high_values.max())
    session_low = float(low_values.min())
    range_position = None
    if session_high > session_low:
        range_position = (last_price - session_low) / (session_high - session_low)

    recent = frame.tail(5)
    mean_volume = float(frame["volume"].mean())
    mean_amount = float(frame["amount"].mean())
    result.update(
        {
            "production_ready": production_ready,
            "latest_timestamp": latest["timestamp"].isoformat(),
            "last_price": _finite(last_price),
            "tail_return_pct": _finite(tail_return),
            "vwap": _finite(vwap),
            "vwap_distance_pct": _finite(
                (last_price / vwap - 1.0) * 100.0 if vwap and vwap > 0 else None
            ),
            "range_position": _finite(range_position),
            "recent_turnover": _finite(float(recent["amount"].sum())),
            "cumulative_volume": _finite(cumulative_volume),
            "cumulative_amount": _finite(cumulative_amount),
            "volume_ratio": _finite(
                float(latest["volume"]) / mean_volume if mean_volume > 0 else None
            ),
            "amount_ratio": _finite(
                float(latest["amount"]) / mean_amount if mean_amount > 0 else None
            ),
        }
    )
    return result


def build_historical_features(
    daily_frame: pd.DataFrame,
    daily_basic_frame: pd.DataFrame,
    moneyflow_frame: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    if daily_frame.empty or "ts_code" not in daily_frame.columns:
        return {}
    required = {"trade_date", "close", "amount"}
    if not required.issubset(daily_frame.columns):
        return {}

    results: dict[str, dict[str, Any]] = {}
    for instrument_id, rows in daily_frame.groupby("ts_code", sort=True):
        daily = rows.sort_values("trade_date", kind="stable").copy()
        daily["close"] = pd.to_numeric(daily["close"], errors="coerce")
        daily["amount"] = pd.to_numeric(daily["amount"], errors="coerce")
        daily = daily.dropna(subset=["close", "amount"])
        if daily.empty:
            continue

        closes = daily["close"].astype(float)
        amounts = daily["amount"].astype(float)
        feature: dict[str, Any] = {
            "latest_trade_date": str(daily.iloc[-1]["trade_date"]),
            "latest_close": _finite(float(closes.iloc[-1])),
            "latest_amount": _finite(float(amounts.iloc[-1])),
            "avg_amount_20d": _finite(float(amounts.tail(20).mean())),
            "return_5d_pct": _window_return(closes, 5),
            "return_20d_pct": _window_return(closes, 20),
            "volatility_20d_pct": _volatility(closes),
            "recent_turnover_rate": None,
        }

        basic = _latest_rows(daily_basic_frame, str(instrument_id))
        if basic is not None and "turnover_rate" in basic.index:
            feature["recent_turnover_rate"] = _finite(basic["turnover_rate"])

        money_rows = _instrument_rows(moneyflow_frame, str(instrument_id))
        if not money_rows.empty:
            latest_money = money_rows.iloc[-1]
            for column in money_rows.columns:
                if column in {"ts_code", "trade_date"}:
                    continue
                feature[column] = _finite(latest_money[column])
            if "net_mf_amount" in money_rows.columns:
                net_values = pd.to_numeric(
                    money_rows["net_mf_amount"], errors="coerce"
                ).dropna()
                feature["net_mf_amount_5d"] = _finite(
                    float(net_values.tail(5).sum()) if not net_values.empty else None
                )
        results[str(instrument_id)] = feature
    return results


def _empty_intraday_features() -> dict[str, Any]:
    return {
        "production_ready": False,
        "latest_timestamp": None,
        "last_price": None,
        "tail_return_pct": None,
        "vwap": None,
        "vwap_distance_pct": None,
        "range_position": None,
        "recent_turnover": None,
        "cumulative_volume": None,
        "cumulative_amount": None,
        "volume_ratio": None,
        "amount_ratio": None,
    }


def _instrument_rows(frame: pd.DataFrame, instrument_id: str) -> pd.DataFrame:
    if frame.empty or "ts_code" not in frame.columns:
        return pd.DataFrame()
    rows = frame[frame["ts_code"].astype(str) == instrument_id].copy()
    if "trade_date" in rows.columns:
        rows = rows.sort_values("trade_date", kind="stable")
    return rows


def _latest_rows(frame: pd.DataFrame, instrument_id: str) -> pd.Series | None:
    rows = _instrument_rows(frame, instrument_id)
    return None if rows.empty else rows.iloc[-1]


def _window_return(closes: pd.Series, periods: int) -> float | None:
    if len(closes) <= periods:
        return None
    previous = float(closes.iloc[-periods - 1])
    if previous <= 0:
        return None
    return _finite((float(closes.iloc[-1]) / previous - 1.0) * 100.0)


def _volatility(closes: pd.Series) -> float | None:
    returns = closes.pct_change(fill_method=None).dropna().tail(20)
    if len(returns) < 2:
        return None
    return _finite(float(returns.std(ddof=0)) * 100.0)


def _shanghai_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize(SHANGHAI)
    return timestamp.tz_convert(SHANGHAI)


def _shanghai_timestamp_or_nat(value: Any) -> pd.Timestamp:
    try:
        return _shanghai_timestamp(value)
    except (TypeError, ValueError):
        return pd.NaT


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number):
        return None
    return round(number, 10)
