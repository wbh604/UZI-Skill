"""Immutable contracts shared by the tail-decision pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping


class InstrumentType(str, Enum):
    STOCK = "stock"
    ETF = "etf"


class DecisionStatus(str, Enum):
    RECOMMENDED = "recommended"
    WATCH_ONLY = "watch_only"
    NO_TRADE = "no_trade"
    BLOCKED = "blocked"


class QualityLevel(str, Enum):
    PASS = "pass"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_positive(value: float, field_name: str) -> None:
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _readonly(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class QuoteSnapshot:
    instrument_id: str
    instrument_type: InstrumentType
    timestamp: datetime
    last_price: float
    open: float
    high: float
    low: float
    pre_close: float
    volume: float
    amount: float
    source: str
    fetched_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.instrument_id, "instrument_id")
        _require_text(self.source, "source")
        _require_aware(self.timestamp, "timestamp")
        _require_aware(self.fetched_at, "fetched_at")
        for field_name in ("last_price", "open", "high", "low", "pre_close"):
            _require_positive(getattr(self, field_name), field_name)
        for field_name in ("volume", "amount"):
            value = getattr(self, field_name)
            if not isfinite(value) or value < 0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True)
class QualityDecision:
    instrument_id: str
    level: QualityLevel
    reasons: tuple[str, ...]
    canonical_quote: QuoteSnapshot | None
    source_quotes: tuple[QuoteSnapshot, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "source_quotes", tuple(self.source_quotes))


@dataclass(frozen=True)
class InstrumentContext:
    instrument_id: str
    name: str
    instrument_type: InstrumentType
    quality: QualityDecision
    quote: QuoteSnapshot | None
    historical: Mapping[str, Any]
    intraday: Mapping[str, Any]
    events: Mapping[str, Any]
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        for field_name in ("historical", "intraday", "events", "metadata"):
            object.__setattr__(self, field_name, _readonly(getattr(self, field_name)))


@dataclass(frozen=True)
class Candidate:
    instrument_id: str
    name: str
    instrument_type: InstrumentType
    score: float
    max_buy_price: float
    lot_size: int
    reasons: tuple[str, ...]
    rejections: tuple[str, ...]
    exit_plan: Mapping[str, Any]
    theme: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "rejections", tuple(self.rejections))
        object.__setattr__(self, "exit_plan", _readonly(self.exit_plan))


@dataclass(frozen=True)
class Allocation:
    instrument_id: str
    quantity: int
    limit_price: float
    notional: float
    candidate_score: float


@dataclass(frozen=True)
class DecisionRun:
    run_id: str
    as_of: datetime
    status: DecisionStatus
    quality: tuple[QualityDecision, ...]
    etf_candidates: tuple[Candidate, ...]
    stock_candidates: tuple[Candidate, ...]
    allocations: tuple[Allocation, ...]
    reasons: tuple[str, ...]
    strategy_version: str
    config_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "quality", tuple(self.quality))
        object.__setattr__(self, "etf_candidates", tuple(self.etf_candidates))
        object.__setattr__(self, "stock_candidates", tuple(self.stock_candidates))
        object.__setattr__(self, "allocations", tuple(self.allocations))
        object.__setattr__(self, "reasons", tuple(self.reasons))
