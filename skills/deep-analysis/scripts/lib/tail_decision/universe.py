"""Deterministic liquid ETF and stock universe from the local archive."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
import re
import pandas as pd


_INSTRUMENT_ID = re.compile(r"^\d{6}\.(?:SH|SZ)$")


class UniverseDataError(RuntimeError):
    """Raised when universe inputs cannot produce a trustworthy contract."""


@dataclass(frozen=True)
class Universe:
    etfs: tuple[str, ...]
    stocks: tuple[str, ...]
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "etfs", tuple(self.etfs))
        object.__setattr__(self, "stocks", tuple(self.stocks))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        for instrument_id in (*self.etfs, *self.stocks):
            if not _INSTRUMENT_ID.fullmatch(instrument_id):
                raise UniverseDataError(
                    f"invalid universe instrument id: {instrument_id!r}"
                )


def build_liquid_universe(
    stock_daily: pd.DataFrame,
    fund_daily: pd.DataFrame,
    stock_basic: pd.DataFrame,
    etf_basic: pd.DataFrame,
    *,
    max_stocks: int = 300,
    max_etfs: int = 30,
    min_stock_amount_cny: float = 0.0,
    min_etf_amount_cny: float = 0.0,
    min_stock_listing_days: int = 60,
    max_stock_lot_notional_cny: float = 12_000.0,
    stock_lot_size: int = 100,
    min_history_sessions: int = 20,
) -> Universe:
    """Rank eligible local instruments by recent average CNY turnover."""

    if max_stocks <= 0 or max_etfs <= 0:
        raise ValueError("universe limits must be positive")
    if min_stock_amount_cny < 0 or min_etf_amount_cny < 0:
        raise ValueError("universe amount thresholds must be non-negative")
    if min_stock_listing_days < 0:
        raise ValueError("min_stock_listing_days must be non-negative")
    if max_stock_lot_notional_cny <= 0:
        raise ValueError("max_stock_lot_notional_cny must be positive")
    if stock_lot_size <= 0:
        raise ValueError("stock_lot_size must be positive")
    if min_history_sessions <= 0:
        raise ValueError("min_history_sessions must be positive")

    stock_as_of = _latest_valid_stock_trade_date(stock_daily)
    stock_ids = _eligible_stock_ids(stock_basic, stock_as_of, min_stock_listing_days)
    etf_ids = _eligible_etf_ids(etf_basic)
    stocks, stock_reasons = _rank_stocks(
        stock_daily,
        eligible=stock_ids,
        limit=max_stocks,
        minimum_cny=min_stock_amount_cny,
        lot_notional_cap_cny=max_stock_lot_notional_cny,
        lot_size=stock_lot_size,
        min_history_sessions=min_history_sessions,
        archive_as_of=stock_as_of,
    )
    etfs = _rank_amount(
        fund_daily,
        eligible=etf_ids,
        limit=max_etfs,
        minimum_cny=min_etf_amount_cny,
        min_history_sessions=min_history_sessions,
    )
    return Universe(etfs=etfs, stocks=stocks, reasons=stock_reasons)


def load_universe_override(path: str | Path) -> Universe | None:
    """Load an explicit ordered universe, or return ``None`` when absent."""

    source = Path(path)
    if not source.is_file():
        return None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("payload must be an object")
        etfs = _override_ids(payload.get("etfs"), "etfs")
        stocks = _override_ids(payload.get("stocks"), "stocks")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise UniverseDataError(f"invalid universe override: {source}") from exc
    if not etfs and not stocks:
        raise UniverseDataError("universe override must contain at least one instrument")
    return Universe(etfs=etfs, stocks=stocks)


def _rank_amount(
    frame: pd.DataFrame,
    *,
    eligible: set[str],
    limit: int,
    minimum_cny: float,
    min_history_sessions: int,
) -> tuple[str, ...]:
    required = {"ts_code", "trade_date", "close", "amount"}
    if frame.empty or not required.issubset(frame.columns) or not eligible:
        return ()
    recent = frame.loc[:, ["ts_code", "trade_date", "close", "amount"]].copy()
    recent["ts_code"] = recent["ts_code"].astype(str).str.upper()
    recent = recent[recent["ts_code"].isin(eligible)]
    recent["trade_date"] = pd.to_datetime(
        recent["trade_date"].astype(str),
        format="%Y%m%d",
        errors="coerce",
    )
    recent["amount_cny"] = pd.to_numeric(
        recent["amount"], errors="coerce"
    ) * 1000.0
    recent["close"] = pd.to_numeric(recent["close"], errors="coerce")
    recent = recent.dropna(subset=["trade_date", "close", "amount_cny"])
    recent = recent[recent["amount_cny"] >= 0.0]
    if recent.empty:
        return ()
    newest = (
        recent.sort_values(["ts_code", "trade_date"], kind="stable")
        .groupby("ts_code", sort=True)
        .tail(min_history_sessions)
    )
    grouped = newest.groupby("ts_code", sort=True)
    averages = grouped["amount_cny"].mean()
    complete = grouped["trade_date"].nunique() >= min_history_sessions
    ranked = averages[
        (averages >= minimum_cny) & complete.reindex(averages.index, fill_value=False)
    ].rename("average_cny").reset_index()
    ranked = ranked.sort_values(
        ["average_cny", "ts_code"],
        ascending=[False, True],
        kind="stable",
    )
    return tuple(ranked.head(limit)["ts_code"].tolist())


def _rank_stocks(
    frame: pd.DataFrame,
    *,
    eligible: set[str],
    limit: int,
    minimum_cny: float,
    lot_notional_cap_cny: float,
    lot_size: int,
    min_history_sessions: int,
    archive_as_of: date | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    required = {"ts_code", "trade_date", "close", "amount"}
    if frame.empty or not required.issubset(frame.columns) or not eligible:
        return (), ()
    recent = _valid_stock_rows(frame, eligible=eligible)
    if recent.empty:
        return (), ()
    latest_sessions = recent.groupby("ts_code", sort=True)["trade_date"].max()
    fresh_ids = set(
        latest_sessions[latest_sessions.eq(pd.Timestamp(archive_as_of))].index
    ) if archive_as_of is not None else set()
    stale_reasons = tuple(
        f"stale_stock:{instrument_id}"
        for instrument_id in sorted(set(latest_sessions.index) - fresh_ids)
    )
    recent = recent[recent["ts_code"].isin(fresh_ids)]
    if recent.empty:
        return (), stale_reasons
    newest = (
        recent.sort_values(["ts_code", "trade_date"], kind="stable")
        .groupby("ts_code", sort=True)
        .tail(min_history_sessions)
    )
    grouped = newest.groupby("ts_code", sort=True)
    averages = grouped["amount_cny"].mean()
    complete = grouped["trade_date"].nunique() >= min_history_sessions
    latest_close = grouped.tail(1).set_index("ts_code")["close"]
    eligible_ids = averages.index[
        (averages >= minimum_cny)
        & complete.reindex(averages.index, fill_value=False)
        & (latest_close.reindex(averages.index) * lot_size <= lot_notional_cap_cny)
    ]
    ranked = averages.loc[eligible_ids].rename("average_cny").reset_index()
    ranked = ranked.sort_values(
        ["average_cny", "ts_code"], ascending=[False, True], kind="stable"
    )
    return tuple(ranked.head(limit)["ts_code"].tolist()), stale_reasons


def _latest_valid_stock_trade_date(frame: pd.DataFrame) -> date | None:
    valid_rows = _valid_stock_rows(frame)
    return valid_rows["trade_date"].max().date() if not valid_rows.empty else None


def _valid_stock_rows(
    frame: pd.DataFrame, *, eligible: set[str] | None = None
) -> pd.DataFrame:
    required = {"ts_code", "trade_date", "close", "amount"}
    if frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame(columns=["ts_code", "trade_date", "close", "amount_cny"])
    rows = frame.loc[:, ["ts_code", "trade_date", "close", "amount"]].copy()
    rows["ts_code"] = rows["ts_code"].astype(str).str.upper()
    rows = rows[rows["ts_code"].map(lambda value: bool(_INSTRUMENT_ID.fullmatch(value)))]
    if eligible is not None:
        rows = rows[rows["ts_code"].isin(eligible)]
    rows["trade_date"] = pd.to_datetime(
        rows["trade_date"].astype(str), format="%Y%m%d", errors="coerce"
    )
    rows["close"] = pd.to_numeric(rows["close"], errors="coerce")
    rows["amount_cny"] = pd.to_numeric(rows["amount"], errors="coerce") * 1000.0
    rows = rows.dropna(subset=["trade_date", "close", "amount_cny"])
    finite = rows["close"].map(math.isfinite) & rows["amount_cny"].map(math.isfinite)
    return rows[finite & (rows["close"] > 0.0) & (rows["amount_cny"] > 0.0)]


def _eligible_stock_ids(
    frame: pd.DataFrame,
    as_of: date | None,
    min_listing_days: int,
) -> set[str]:
    required = {"ts_code", "name", "list_date"}
    if frame.empty or not required.issubset(frame.columns) or as_of is None:
        return set()
    masters = frame.loc[:, ["ts_code", "name", "list_date"]].copy()
    masters["ts_code"] = masters["ts_code"].astype(str).str.upper()
    masters["name"] = masters["name"].fillna("").astype(str).str.strip()
    masters["list_date"] = pd.to_datetime(
        masters["list_date"].astype(str),
        format="%Y%m%d",
        errors="coerce",
    )
    names = masters["name"].str.upper()
    listing_age = pd.Timestamp(as_of) - masters["list_date"]
    eligible = masters[
        masters["ts_code"].map(lambda value: bool(_INSTRUMENT_ID.fullmatch(value)))
        & ~names.str.startswith(("ST", "*ST"))
        & ~masters["name"].str.contains("退", regex=False)
        & masters["list_date"].notna()
        & (listing_age.dt.days >= min_listing_days)
    ]
    return set(eligible["ts_code"].tolist())


def _eligible_etf_ids(frame: pd.DataFrame) -> set[str]:
    required = {"ts_code", "list_status"}
    if frame.empty or not required.issubset(frame.columns):
        return set()
    codes = frame["ts_code"].astype(str).str.upper()
    listed = frame["list_status"].astype(str).str.upper().eq("L")
    return {
        instrument_id
        for instrument_id in codes[listed]
        if _INSTRUMENT_ID.fullmatch(instrument_id)
    }


def _latest_trade_date(*frames: pd.DataFrame) -> date | None:
    values: list[pd.Timestamp] = []
    for frame in frames:
        if frame.empty or "trade_date" not in frame.columns:
            continue
        parsed = pd.to_datetime(
            frame["trade_date"].astype(str),
            format="%Y%m%d",
            errors="coerce",
        ).dropna()
        if not parsed.empty:
            values.append(parsed.max())
    return max(values).date() if values else None


def _override_ids(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} entries must be strings")
        instrument_id = item.strip().upper()
        if not _INSTRUMENT_ID.fullmatch(instrument_id):
            raise ValueError(f"invalid instrument id: {item!r}")
        if instrument_id not in normalized:
            normalized.append(instrument_id)
    return tuple(normalized)
