"""Deterministic liquid ETF and stock universe from the local archive."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "etfs", tuple(self.etfs))
        object.__setattr__(self, "stocks", tuple(self.stocks))
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
    max_stocks: int = 20,
    max_etfs: int = 10,
    min_stock_amount_cny: float = 0.0,
    min_etf_amount_cny: float = 0.0,
    min_stock_listing_days: int = 60,
) -> Universe:
    """Rank eligible local instruments by recent average CNY turnover."""

    if max_stocks <= 0 or max_etfs <= 0:
        raise ValueError("universe limits must be positive")
    if min_stock_amount_cny < 0 or min_etf_amount_cny < 0:
        raise ValueError("universe amount thresholds must be non-negative")
    if min_stock_listing_days < 0:
        raise ValueError("min_stock_listing_days must be non-negative")

    as_of = _latest_trade_date(stock_daily, fund_daily)
    stock_ids = _eligible_stock_ids(stock_basic, as_of, min_stock_listing_days)
    etf_ids = _eligible_etf_ids(etf_basic)
    stocks = _rank_amount(
        stock_daily,
        eligible=stock_ids,
        limit=max_stocks,
        minimum_cny=min_stock_amount_cny,
    )
    etfs = _rank_amount(
        fund_daily,
        eligible=etf_ids,
        limit=max_etfs,
        minimum_cny=min_etf_amount_cny,
    )
    return Universe(etfs=etfs, stocks=stocks)


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
) -> tuple[str, ...]:
    required = {"ts_code", "trade_date", "amount"}
    if frame.empty or not required.issubset(frame.columns) or not eligible:
        return ()
    recent = frame.loc[:, ["ts_code", "trade_date", "amount"]].copy()
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
    recent = recent.dropna(subset=["trade_date", "amount_cny"])
    recent = recent[recent["amount_cny"] >= 0.0]
    if recent.empty:
        return ()
    newest = (
        recent.sort_values(["ts_code", "trade_date"], kind="stable")
        .groupby("ts_code", sort=True)
        .tail(20)
    )
    averages = newest.groupby("ts_code", sort=True)["amount_cny"].mean()
    ranked = averages[averages >= minimum_cny].rename("average_cny").reset_index()
    ranked = ranked.sort_values(
        ["average_cny", "ts_code"],
        ascending=[False, True],
        kind="stable",
    )
    return tuple(ranked.head(limit)["ts_code"].tolist())


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
