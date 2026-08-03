"""Validated configuration for the self-sustaining tail-decision system."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json

from .contracts import InstrumentType


@dataclass(frozen=True)
class DecisionConfig:
    account_assets: float = 10_000.0
    max_total_exposure: float = 8_000.0
    max_instrument_exposure: float = 4_000.0
    max_etf_candidates: int = 2
    max_stock_candidates: int = 2
    min_etf_daily_amount: float = 50_000_000.0
    max_etf_premium_pct: float = 1.0
    etf_nav_stale_minutes: int = 30
    etf_excessive_daily_gain_pct: float = 5.0
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
        if not 0 < self.max_total_exposure <= self.account_assets:
            raise ValueError("max_total_exposure must be positive and not exceed account_assets")
        if not 0 < self.max_instrument_exposure <= self.max_total_exposure:
            raise ValueError(
                "max_instrument_exposure must be positive and not exceed max_total_exposure"
            )

        for field_name in (
            "max_etf_candidates",
            "max_stock_candidates",
            "etf_nav_stale_minutes",
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

        decision_start = _parse_time(self.decision_start, "decision_start")
        final_decision_time = _parse_time(
            self.final_decision_time, "final_decision_time"
        )
        if final_decision_time <= decision_start:
            raise ValueError("final_decision_time must be after decision_start")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")

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
