"""Validated configuration for the self-sustaining tail-decision system."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json

from .contracts import InstrumentType


@dataclass(frozen=True)
class DecisionConfig:
    account_assets: float = 12_000.0
    configured_position_cap_cny: float = 12_000.0
    available_cash_cny: float | None = 12_000.0
    research_stock_limit: int = 300
    realtime_stock_limit: int = 30
    realtime_etf_limit: int = 10
    max_etf_candidates: int = 2
    max_stock_candidates: int = 3
    min_etf_daily_amount: float = 50_000_000.0
    max_etf_premium_pct: float = 1.0
    etf_nav_stale_minutes: int = 30
    etf_excessive_daily_gain_pct: float = 5.0
    min_stock_daily_amount: float = 300_000_000.0
    min_stock_listing_days: int = 60
    max_stock_daily_gain_pct: float = 9.2
    near_limit_distance_pct: float = 0.5
    max_quote_age_seconds: int = 60
    max_price_deviation_pct: float = 0.3
    min_sources_for_recommendation: int = 2
    decision_start: str = "14:10"
    final_decision_time: str = "14:30"
    strategy_version: str = "tail-v1"
    stock_lot_size: int = 100
    etf_default_lot_size: int = 100
    stock_commission_rate: float = 0.0003
    etf_commission_rate: float = 0.0003
    minimum_commission: float = 5.0
    stock_sell_stamp_tax_rate: float = 0.0005
    buy_slippage_bps: float = 5.0
    sell_slippage_bps: float = 5.0

    def __post_init__(self) -> None:
        if self.account_assets <= 0:
            raise ValueError("account_assets must be positive")
        if self.configured_position_cap_cny <= 0:
            raise ValueError("configured_position_cap_cny must be positive")
        if self.available_cash_cny is not None and self.available_cash_cny <= 0:
            raise ValueError("available_cash_cny must be positive")

        for field_name in (
            "research_stock_limit",
            "realtime_stock_limit",
            "realtime_etf_limit",
            "max_etf_candidates",
            "max_stock_candidates",
            "etf_nav_stale_minutes",
            "min_stock_listing_days",
            "max_quote_age_seconds",
            "min_sources_for_recommendation",
            "stock_lot_size",
            "etf_default_lot_size",
        ):
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be positive")

        for field_name in (
            "max_price_deviation_pct",
            "max_etf_premium_pct",
            "etf_excessive_daily_gain_pct",
            "max_stock_daily_gain_pct",
            "near_limit_distance_pct",
            "stock_commission_rate",
            "etf_commission_rate",
            "minimum_commission",
            "stock_sell_stamp_tax_rate",
            "buy_slippage_bps",
            "sell_slippage_bps",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")

        if self.min_etf_daily_amount <= 0:
            raise ValueError("min_etf_daily_amount must be positive")
        if self.min_stock_daily_amount <= 0:
            raise ValueError("min_stock_daily_amount must be positive")

        decision_start = _parse_time(self.decision_start, "decision_start")
        final_decision_time = _parse_time(
            self.final_decision_time, "final_decision_time"
        )
        if final_decision_time <= decision_start:
            raise ValueError("final_decision_time must be after decision_start")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")

    @property
    def effective_position_cap_cny(self) -> float | None:
        if self.available_cash_cny is None:
            return None
        return min(self.configured_position_cap_cny, self.available_cash_cny)

    @property
    def max_total_exposure(self) -> float | None:
        return self.effective_position_cap_cny

    @property
    def max_instrument_exposure(self) -> float | None:
        return self.effective_position_cap_cny

    def lot_size_for(self, instrument_type: InstrumentType) -> int:
        if instrument_type is InstrumentType.STOCK:
            return self.stock_lot_size
        if instrument_type is InstrumentType.ETF:
            return self.etf_default_lot_size
        raise ValueError(f"unsupported instrument type: {instrument_type!r}")


def _parse_time(value: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError(f"{field_name} must use HH:MM format") from exc


def config_hash(config: DecisionConfig) -> str:
    canonical = json.dumps(
        asdict(config),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(canonical).hexdigest()
