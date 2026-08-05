"""Credential-free realtime quote providers with per-provider isolation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import re
import time
from typing import Iterable, Protocol, Sequence

import requests

from .contracts import InstrumentType, QuoteSnapshot


class QuoteProvider(Protocol):
    name: str

    def fetch_quotes(
        self, ids: Sequence[str], now: datetime
    ) -> dict[str, QuoteSnapshot]: ...


def _split_instrument_id(instrument_id: str) -> tuple[str, str]:
    try:
        code, exchange = instrument_id.upper().split(".", 1)
    except ValueError as exc:
        raise ValueError(f"invalid instrument id: {instrument_id!r}") from exc
    if len(code) != 6 or not code.isdigit() or exchange not in {"SH", "SZ"}:
        raise ValueError(f"invalid instrument id: {instrument_id!r}")
    return code, exchange


def _instrument_type(instrument_id: str) -> InstrumentType:
    code, _ = _split_instrument_id(instrument_id)
    if code.startswith(("5", "15", "16")):
        return InstrumentType.ETF
    return InstrumentType.STOCK


def _eastmoney_secid(instrument_id: str) -> str:
    code, exchange = _split_instrument_id(instrument_id)
    return f"{'1' if exchange == 'SH' else '0'}.{code}"


def _tencent_symbol(instrument_id: str) -> str:
    code, exchange = _split_instrument_id(instrument_id)
    return f"{exchange.lower()}{code}"


class EastmoneyQuoteProvider:
    name = "eastmoney"
    endpoint = "https://push2.eastmoney.com/api/qt/stock/get"
    fields = "f43,f44,f45,f46,f47,f48,f57,f58,f59,f60,f124"

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 8.0,
        max_workers: int = 8,
        max_attempts: int = 2,
        retry_backoff_seconds: float = 0.2,
    ):
        if max_workers <= 0 or max_workers > 8:
            raise ValueError("max_workers must be between 1 and 8")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be non-negative")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_workers = max_workers
        self.max_attempts = max_attempts
        self.retry_backoff_seconds = retry_backoff_seconds

    @staticmethod
    def parse_payload(
        instrument_id: str, payload: dict, fetched_at: datetime
    ) -> QuoteSnapshot:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("eastmoney payload has no data")
        precision = int(data.get("f59", 2))
        scale = 10**precision

        def price(field: str) -> float:
            return float(data[field]) / scale

        quote_timestamp = datetime.fromtimestamp(
            int(data.get("f124") or fetched_at.timestamp()), tz=fetched_at.tzinfo
        )
        return QuoteSnapshot(
            instrument_id=instrument_id,
            instrument_type=_instrument_type(instrument_id),
            timestamp=quote_timestamp,
            last_price=price("f43"),
            open=price("f46"),
            high=price("f44"),
            low=price("f45"),
            pre_close=price("f60"),
            volume=float(data.get("f47") or 0) * 100.0,
            amount=float(data.get("f48") or 0),
            source="eastmoney",
            fetched_at=fetched_at,
        )

    def fetch_quotes(
        self, ids: Sequence[str], now: datetime
    ) -> dict[str, QuoteSnapshot]:
        quotes: dict[str, QuoteSnapshot] = {}
        requested = tuple(dict.fromkeys(ids))
        if not requested:
            return quotes
        with ThreadPoolExecutor(
            max_workers=min(self.max_workers, len(requested)),
            thread_name_prefix="eastmoney-quote",
        ) as executor:
            futures = {
                executor.submit(self._fetch_one, instrument_id, now): instrument_id
                for instrument_id in requested
            }
            for future in as_completed(futures):
                instrument_id = futures[future]
                try:
                    quotes[instrument_id] = future.result()
                except Exception:
                    continue
        return quotes

    def _fetch_one(self, instrument_id: str, now: datetime) -> QuoteSnapshot:
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(
                    self.endpoint,
                    params={
                        "secid": _eastmoney_secid(instrument_id),
                        "fields": self.fields,
                    },
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return self.parse_payload(instrument_id, response.json(), now)
            except requests.RequestException:
                if attempt >= self.max_attempts:
                    raise
                if self.retry_backoff_seconds:
                    time.sleep(self.retry_backoff_seconds * attempt)
        raise RuntimeError("unreachable eastmoney retry state")


class TencentQuoteProvider:
    name = "tencent"
    endpoint = "https://qt.gtimg.cn/"

    def __init__(self, session: requests.Session | None = None, timeout: float = 8.0):
        self.session = session or requests.Session()
        self.timeout = timeout

    @staticmethod
    def parse_response(text: str, fetched_at: datetime) -> dict[str, QuoteSnapshot]:
        quotes: dict[str, QuoteSnapshot] = {}
        for symbol, payload in re.findall(r'v_((?:sh|sz)\d{6})="([^"]*)"', text):
            parts = payload.split("~")
            if len(parts) < 38:
                continue
            try:
                exchange = "SH" if symbol.startswith("sh") else "SZ"
                instrument_id = f"{symbol[2:]}.{exchange}"
                timestamp = fetched_at
                if parts[30]:
                    timestamp = datetime.strptime(parts[30], "%Y%m%d%H%M%S").replace(
                        tzinfo=fetched_at.tzinfo
                    )
                quotes[instrument_id] = QuoteSnapshot(
                    instrument_id=instrument_id,
                    instrument_type=_instrument_type(instrument_id),
                    timestamp=timestamp,
                    last_price=float(parts[3]),
                    open=float(parts[5]),
                    high=float(parts[33]),
                    low=float(parts[34]),
                    pre_close=float(parts[4]),
                    volume=float(parts[6] or 0) * 100.0,
                    amount=float(parts[37] or 0) * 10_000.0,
                    source="tencent",
                    fetched_at=fetched_at,
                )
            except (IndexError, TypeError, ValueError):
                continue
        return quotes

    def fetch_quotes(
        self, ids: Sequence[str], now: datetime
    ) -> dict[str, QuoteSnapshot]:
        symbols = ",".join(_tencent_symbol(instrument_id) for instrument_id in ids)
        response = self.session.get(
            self.endpoint,
            params={"q": symbols},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        response.encoding = "gbk"
        return self.parse_response(response.text, now)


def fetch_from_providers(
    providers: Iterable[QuoteProvider], ids: Sequence[str], now: datetime
) -> dict[str, list[QuoteSnapshot]]:
    requested = tuple(dict.fromkeys(ids))
    combined: dict[str, list[QuoteSnapshot]] = {
        instrument_id: [] for instrument_id in requested
    }
    for provider in providers:
        try:
            quotes = provider.fetch_quotes(requested, now)
        except Exception:
            continue
        for instrument_id, quote in quotes.items():
            if instrument_id in combined:
                combined[instrument_id].append(quote)
    return combined
