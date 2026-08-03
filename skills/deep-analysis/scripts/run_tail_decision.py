#!/usr/bin/env python
"""Run the self-sustaining tail-decision workflow without paid credentials."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any
from zoneinfo import ZoneInfo

from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.contracts import (
    DecisionStatus,
    InstrumentContext,
    InstrumentType,
    QuoteSnapshot,
)
from lib.tail_decision.etf_strategy import rank_etfs
from lib.tail_decision.portfolio import allocate_portfolio
from lib.tail_decision.quality import evaluate_quote_quality
from lib.tail_decision.recorder import DecisionRecorder
from lib.tail_decision.stock_strategy import rank_overnight_stocks
from lib.tail_decision.workflow import TailDecisionWorkflow, WorkflowInputs


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_ROOT = PROJECT_ROOT.parent / "data" / "tushare_calendar"
DEFAULT_ETFS = ("513050.SH",)
DEFAULT_STOCKS = ("600406.SH",)


class _OfflineGateway:
    def collect(self, *, as_of: datetime, phase: str) -> WorkflowInputs:
        etf_quotes = _fixture_quotes(
            "513050.SH",
            InstrumentType.ETF,
            as_of,
            price=1.18,
            pre_close=1.16,
            amount=2_000_000_000.0,
        )
        stock_quotes = _fixture_quotes(
            "600406.SH",
            InstrumentType.STOCK,
            as_of,
            price=25.0,
            pre_close=24.5,
            amount=500_000_000.0,
        )
        etf_quality = evaluate_quote_quality(
            "513050.SH", etf_quotes, as_of, self.config
        )
        stock_quality = evaluate_quote_quality(
            "600406.SH", stock_quotes, as_of, self.config
        )
        etf = InstrumentContext(
            instrument_id="513050.SH",
            name="fixture-etf",
            instrument_type=InstrumentType.ETF,
            quality=etf_quality,
            quote=etf_quality.canonical_quote,
            historical={
                "avg_amount_20d": 2_000_000_000.0,
                "latest_amount": 2_000_000_000.0,
                "daily_gain_pct": 1.0,
                "net_mf_amount": 40_000_000.0,
            },
            intraday={
                "production_ready": True,
                "tail_return_pct": 1.2,
                "vwap_distance_pct": 0.4,
                "range_position": 0.8,
                "volume_ratio": 1.2,
            },
            events={},
            metadata={
                "lot_size": 100,
                "tracking_index": "fixture-index",
                "premium_proxy_pct": 0.0,
                "nav_age_minutes": 1,
                "underlying_market_open": True,
                "theme": "fixture-etf-theme",
            },
        )
        stock = InstrumentContext(
            instrument_id="600406.SH",
            name="fixture-stock",
            instrument_type=InstrumentType.STOCK,
            quality=stock_quality,
            quote=stock_quality.canonical_quote,
            historical={
                "avg_amount_20d": 500_000_000.0,
                "daily_gain_pct": 2.04,
                "return_20d_pct": 4.0,
                "volatility_20d_pct": 1.5,
                "net_mf_amount": 10_000_000.0,
                "net_mf_amount_5d": 25_000_000.0,
                "sector_relative_strength": 0.5,
            },
            intraday={
                "production_ready": True,
                "tail_return_pct": 1.0,
                "vwap_distance_pct": 0.2,
                "range_position": 0.7,
                "amount_ratio": 1.2,
            },
            events={"adverse_event": False},
            metadata={
                "lot_size": 100,
                "is_st": False,
                "delisting": False,
                "suspended": False,
                "listing_days": 365,
                "theme": "fixture-stock-theme",
            },
        )
        return WorkflowInputs(
            quality=(etf_quality, stock_quality),
            etf_contexts=(etf,),
            stock_contexts=(stock,),
            raw_quotes={
                "mode": "offline_fixture",
                "phase": phase,
                "513050.SH": etf_quotes,
                "600406.SH": stock_quotes,
            },
        )

    def __init__(self, config: DecisionConfig) -> None:
        self.config = config


class _CredentialFreeGateway:
    def __init__(self, config: DecisionConfig, data_root: Path) -> None:
        self.config = config
        self.data_root = data_root
        self.etfs, self.stocks = _load_universe(data_root)

    def collect(self, *, as_of: datetime, phase: str) -> WorkflowInputs:
        from lib.tail_decision.free_quotes import (
            EastmoneyQuoteProvider,
            TencentQuoteProvider,
            fetch_from_providers,
        )

        instrument_ids = (*self.etfs, *self.stocks)
        quotes = fetch_from_providers(
            (EastmoneyQuoteProvider(), TencentQuoteProvider()),
            instrument_ids,
            as_of,
        )
        quality = tuple(
            evaluate_quote_quality(
                instrument_id,
                quotes[instrument_id],
                as_of,
                self.config,
            )
            for instrument_id in instrument_ids
        )
        quality_by_id = {item.instrument_id: item for item in quality}
        etf_contexts = tuple(
            _live_context(instrument_id, InstrumentType.ETF, quality_by_id[instrument_id])
            for instrument_id in self.etfs
        )
        stock_contexts = tuple(
            _live_context(
                instrument_id,
                InstrumentType.STOCK,
                quality_by_id[instrument_id],
            )
            for instrument_id in self.stocks
        )
        return WorkflowInputs(
            quality=quality,
            etf_contexts=etf_contexts,
            stock_contexts=stock_contexts,
            raw_quotes={"mode": "credential_free", "phase": phase, "quotes": quotes},
        )


def _fixture_quotes(
    instrument_id: str,
    instrument_type: InstrumentType,
    as_of: datetime,
    *,
    price: float,
    pre_close: float,
    amount: float,
) -> tuple[QuoteSnapshot, QuoteSnapshot]:
    common = {
        "instrument_id": instrument_id,
        "instrument_type": instrument_type,
        "timestamp": as_of,
        "last_price": price,
        "open": pre_close,
        "high": max(price, pre_close),
        "low": min(price, pre_close),
        "pre_close": pre_close,
        "volume": 100_000.0,
        "amount": amount,
        "fetched_at": as_of,
    }
    return (
        QuoteSnapshot(source="eastmoney", **common),
        QuoteSnapshot(source="tencent", **common),
    )


def _live_context(instrument_id, instrument_type, quality) -> InstrumentContext:
    quote = quality.canonical_quote
    amount = quote.amount if quote is not None else 0.0
    metadata: dict[str, Any] = {"lot_size": 100}
    events: dict[str, Any] = {}
    if instrument_type is InstrumentType.ETF:
        metadata.update(
            tracking_index="local-universe",
            premium_proxy_pct=None,
            theme=instrument_id,
        )
    else:
        metadata.update(
            is_st=False,
            delisting=False,
            suspended=False,
            listing_days=365,
            theme=instrument_id,
        )
        events["adverse_event"] = True
    return InstrumentContext(
        instrument_id=instrument_id,
        name=instrument_id,
        instrument_type=instrument_type,
        quality=quality,
        quote=quote,
        historical={"avg_amount_20d": amount, "latest_amount": amount},
        intraday={"production_ready": False},
        events=events,
        metadata=metadata,
    )


def _load_universe(data_root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    universe_path = data_root / "tail_decision_universe.json"
    if not universe_path.is_file():
        return DEFAULT_ETFS, DEFAULT_STOCKS
    payload = json.loads(universe_path.read_text(encoding="utf-8"))
    etfs = tuple(str(item) for item in payload.get("etfs", ()))
    stocks = tuple(str(item) for item in payload.get("stocks", ()))
    if not etfs and not stocks:
        raise ValueError("tail-decision universe is empty")
    return etfs, stocks


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        required=True,
        choices=("warmup", "preview", "final", "close", "exit_open", "exit_check"),
    )
    parser.add_argument("--as-of")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--account-assets", type=float, default=10_000.0)
    parser.add_argument("--max-exposure", type=float, default=8_000.0)
    parser.add_argument("--offline-fixture", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = DecisionConfig(
            account_assets=args.account_assets,
            max_total_exposure=args.max_exposure,
            max_instrument_exposure=min(4_000.0, args.max_exposure),
        )
        as_of = (
            datetime.fromisoformat(args.as_of)
            if args.as_of
            else datetime.now(ZoneInfo("Asia/Shanghai"))
        )
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("--as-of must include a UTC offset")
        gateway = (
            _OfflineGateway(config)
            if args.offline_fixture
            else _CredentialFreeGateway(config, args.data_root)
        )
        workflow = TailDecisionWorkflow(
            config=config,
            gateway=gateway,
            etf_ranker=rank_etfs,
            stock_ranker=rank_overnight_stocks,
            allocator=allocate_portfolio,
            recorder=DecisionRecorder(args.output_root),
        )
        run = workflow.run(as_of=as_of, phase=args.phase)
    except ValueError as exc:
        print(f"invalid configuration: {exc}", file=sys.stderr)
        print(json.dumps({"status": "blocked", "reasons": ["invalid_configuration"]}))
        return 3
    except Exception as exc:
        print(f"tail-decision failure: {type(exc).__name__}", file=sys.stderr)
        print(json.dumps({"status": "blocked", "reasons": ["runtime_failure"]}))
        return 2

    payload = {
        "run_id": run.run_id,
        "phase": args.phase,
        "as_of": run.as_of.isoformat(),
        "status": run.status.value,
        "total_exposure": round(sum(item.notional for item in run.allocations), 2),
        "allocations": [
            {
                "instrument_id": item.instrument_id,
                "quantity": item.quantity,
                "limit_price": item.limit_price,
                "notional": item.notional,
            }
            for item in run.allocations
        ],
        "reasons": list(run.reasons),
    }
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 2 if run.status is DecisionStatus.BLOCKED else 0


if __name__ == "__main__":
    raise SystemExit(main())
