"""Production credential-free gateway for the tail-decision workflow."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from statistics import median
from typing import Mapping, Sequence

import pandas as pd

from .config import DecisionConfig
from .contracts import InstrumentContext, InstrumentType
from .event_risk import evaluate_event_risk
from .features import build_historical_features, build_intraday_features
from .free_quotes import QuoteProvider, fetch_from_providers
from .quality import evaluate_quote_quality
from .universe import Universe, build_liquid_universe
from .workflow import WorkflowInputs


class CredentialFreeGateway:
    """Compose local archive evidence and free realtime sources without tokens."""

    def __init__(
        self,
        *,
        config: DecisionConfig,
        archive_reader,
        snapshot_store,
        quote_providers: Sequence[QuoteProvider],
        announcement_provider,
        universe_override: Universe | None = None,
    ) -> None:
        self.config = config
        self.archive_reader = archive_reader
        self.snapshot_store = snapshot_store
        self.quote_providers = tuple(quote_providers)
        self.announcement_provider = announcement_provider
        self.universe_override = universe_override

    def collect(self, *, as_of: datetime, phase: str) -> WorkflowInputs:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")

        archive = self._read_archive(as_of)
        universe = self.universe_override or build_liquid_universe(
            archive["daily"],
            archive["fund_daily"],
            archive["stock_basic"],
            archive["etf_basic"],
            min_stock_amount_cny=self.config.min_stock_daily_amount,
            min_etf_amount_cny=self.config.min_etf_daily_amount,
            min_stock_listing_days=self.config.min_stock_listing_days,
        )
        instrument_ids = (*universe.etfs, *universe.stocks)
        if not instrument_ids:
            return WorkflowInputs(system_errors=("empty_eligible_universe",))

        quotes = fetch_from_providers(self.quote_providers, instrument_ids, as_of)
        if any(quotes.values()):
            self._append_quotes_by_date(phase=phase, quotes=quotes, as_of=as_of)

        quality = tuple(
            evaluate_quote_quality(
                instrument_id,
                quotes.get(instrument_id, ()),
                as_of,
                self.config,
            )
            for instrument_id in instrument_ids
        )
        quality_by_id = {item.instrument_id: item for item in quality}

        daily = _amounts_to_cny(archive["daily"])
        fund_daily = _amounts_to_cny(archive["fund_daily"])
        moneyflow = _amounts_to_cny(archive["moneyflow"])
        stock_history = build_historical_features(
            daily,
            archive["daily_basic"],
            moneyflow,
        )
        etf_history = build_historical_features(
            fund_daily,
            pd.DataFrame(),
            pd.DataFrame(),
        )

        previous_close = self._previous_trading_close(as_of)
        etf_contexts = tuple(
            self._etf_context(
                instrument_id,
                as_of,
                quality_by_id[instrument_id],
                etf_history.get(instrument_id, {}),
                archive["etf_basic"],
            )
            for instrument_id in universe.etfs
        )
        stock_contexts = tuple(
            self._stock_context(
                instrument_id,
                as_of,
                quality_by_id[instrument_id],
                stock_history.get(instrument_id, {}),
                archive,
                previous_close,
            )
            for instrument_id in universe.stocks
        )
        return WorkflowInputs(
            quality=quality,
            etf_contexts=etf_contexts,
            stock_contexts=stock_contexts,
            raw_quotes={
                "mode": "credential_free",
                "phase": phase,
                "quotes": quotes,
            },
        )

    def _append_quotes_by_date(self, *, phase: str, quotes, as_of: datetime) -> None:
        grouped: dict[str, dict[str, list[object]]] = {}
        for instrument_id, snapshots in quotes.items():
            for snapshot in snapshots:
                day = snapshot.timestamp.astimezone(as_of.tzinfo).strftime("%Y%m%d")
                grouped.setdefault(day, {}).setdefault(instrument_id, []).append(
                    snapshot
                )
        for day in sorted(grouped):
            self.snapshot_store.append(phase=phase, quotes=grouped[day])

    def _read_archive(self, as_of: datetime) -> dict[str, pd.DataFrame]:
        return {
            "daily": self.archive_reader.read_recent("daily", as_of, 20),
            "fund_daily": self.archive_reader.read_recent("fund_daily", as_of, 20),
            "daily_basic": self.archive_reader.read_recent(
                "daily_basic", as_of, 20, required=False
            ),
            "moneyflow": self.archive_reader.read_recent(
                "moneyflow", as_of, 20, required=False
            ),
            "stock_basic": self.archive_reader.read_static(
                "stock_basic", ("listed.csv.gz",)
            ),
            "etf_basic": self.archive_reader.read_latest("etf_basic", as_of),
            "stock_st": self.archive_reader.read_latest(
                "stock_st", as_of, required=False
            ),
            "suspend_d": self.archive_reader.read_latest(
                "suspend_d", as_of, required=False
            ),
            "stk_limit": self.archive_reader.read_latest(
                "stk_limit", as_of, required=False
            ),
        }

    def _etf_context(
        self,
        instrument_id: str,
        as_of: datetime,
        quality,
        historical: Mapping[str, object],
        etf_basic: pd.DataFrame,
    ) -> InstrumentContext:
        master = _row_for(etf_basic, instrument_id)
        quote = quality.canonical_quote
        history = dict(historical)
        _attach_daily_gain(history, quote)
        name = _first_text(master, "csname", "name", "fund_name") or instrument_id
        tracking = _first_text(
            master,
            "index_code",
            "tracking_index",
            "tracking_target",
            "benchmark",
        )
        premium_proxy = _cross_source_price_deviation(quality.source_quotes)
        metadata = {
            "name": name,
            "lot_size": self.config.etf_default_lot_size,
            "tracking_index": tracking,
            "tracking_target": tracking,
            "premium_proxy_pct": premium_proxy,
            "premium_proxy_source": "cross_source_price_deviation",
            "nav_age_minutes": None,
            "underlying_market_open": True,
            "theme": tracking or instrument_id,
        }
        return InstrumentContext(
            instrument_id=instrument_id,
            name=name,
            instrument_type=InstrumentType.ETF,
            quality=quality,
            quote=quote,
            historical=history,
            intraday=build_intraday_features(
                self.snapshot_store.read_intraday(instrument_id, as_of), as_of
            ),
            events={},
            metadata=metadata,
        )

    def _stock_context(
        self,
        instrument_id: str,
        as_of: datetime,
        quality,
        historical: Mapping[str, object],
        archive: Mapping[str, pd.DataFrame],
        previous_close: datetime,
    ) -> InstrumentContext:
        master = _row_for(archive["stock_basic"], instrument_id)
        st_row = _row_for(archive["stock_st"], instrument_id)
        suspend_row = _row_for(archive["suspend_d"], instrument_id)
        limit_row = _row_for(archive["stk_limit"], instrument_id)
        quote = quality.canonical_quote
        history = dict(historical)
        _attach_daily_gain(history, quote)
        name = _first_text(master, "name") or instrument_id

        try:
            announcements = self.announcement_provider.fetch(instrument_id, as_of)
        except Exception:
            events = evaluate_event_risk((), source_ok=False)
        else:
            events = evaluate_event_risk(
                announcements,
                source_ok=True,
                since=previous_close,
                as_of=as_of,
            )

        list_date = _parse_archive_date(master.get("list_date")) if master else None
        listing_days = (as_of.date() - list_date).days if list_date else None
        metadata = {
            "name": name,
            "lot_size": self.config.stock_lot_size,
            "industry": _first_text(master, "industry"),
            "sector": _first_text(master, "industry"),
            "theme": _first_text(master, "industry") or instrument_id,
            "is_st": st_row is not None or name.upper().startswith(("ST", "*ST")),
            "delisting": "退" in name,
            "suspended": suspend_row is not None,
            "listing_days": listing_days,
            "limit_up": _first_number(limit_row, "up_limit", "limit_up"),
            "limit_down": _first_number(limit_row, "down_limit", "limit_down"),
        }
        return InstrumentContext(
            instrument_id=instrument_id,
            name=name,
            instrument_type=InstrumentType.STOCK,
            quality=quality,
            quote=quote,
            historical=history,
            intraday=build_intraday_features(
                self.snapshot_store.read_intraday(instrument_id, as_of), as_of
            ),
            events=events,
            metadata=metadata,
        )

    def _previous_trading_close(self, as_of: datetime) -> datetime:
        dates = self.archive_reader.read_trade_dates(
            as_of.date() - timedelta(days=14), as_of.date()
        )
        prior = [value for value in dates if value < as_of.strftime("%Y%m%d")]
        if not prior:
            raise ValueError("previous trading date is unavailable")
        previous_date = datetime.strptime(max(prior), "%Y%m%d").date()
        return datetime.combine(previous_date, time(15, 0), tzinfo=as_of.tzinfo)


def _amounts_to_cny(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in normalized.columns:
        if column == "amount" or column.endswith("_amount"):
            normalized[column] = pd.to_numeric(
                normalized[column], errors="coerce"
            ) * 1000.0
    return normalized


def _row_for(frame: pd.DataFrame, instrument_id: str) -> dict[str, object] | None:
    if frame.empty or "ts_code" not in frame.columns:
        return None
    rows = frame[frame["ts_code"].astype(str).str.upper() == instrument_id]
    if rows.empty:
        return None
    return rows.iloc[-1].to_dict()


def _first_text(row: Mapping[str, object] | None, *columns: str) -> str | None:
    if row is None:
        return None
    for column in columns:
        value = row.get(column)
        if value is not None and not pd.isna(value) and str(value).strip():
            return str(value).strip()
    return None


def _first_number(row: Mapping[str, object] | None, *columns: str) -> float | None:
    if row is None:
        return None
    for column in columns:
        value = pd.to_numeric(row.get(column), errors="coerce")
        if not pd.isna(value):
            return float(value)
    return None


def _parse_archive_date(value: object):
    parsed = pd.to_datetime(str(value), format="%Y%m%d", errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def _attach_daily_gain(history: dict[str, object], quote) -> None:
    if quote is not None and quote.pre_close > 0:
        history["daily_gain_pct"] = (
            quote.last_price / quote.pre_close - 1.0
        ) * 100.0


def _cross_source_price_deviation(quotes) -> float | None:
    prices = [float(item.last_price) for item in quotes]
    if len(prices) < 2:
        return None
    center = median(prices)
    if center <= 0:
        return None
    return (max(prices) - min(prices)) / center * 100.0
