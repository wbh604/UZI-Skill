"""Phase-aware orchestration and status resolution for tail decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .config import DecisionConfig, config_hash
from .contracts import (
    Allocation,
    Candidate,
    DecisionRun,
    DecisionStatus,
    InstrumentContext,
    QualityDecision,
    QualityLevel,
)


_PHASES = frozenset(
    {"warmup", "preview", "final", "close", "exit_open", "exit_check"}
)


@dataclass(frozen=True)
class WorkflowInputs:
    system_errors: tuple[str, ...] = ()
    quality: tuple[QualityDecision, ...] = ()
    etf_contexts: tuple[InstrumentContext, ...] = ()
    stock_contexts: tuple[InstrumentContext, ...] = ()
    raw_quotes: Mapping[str, Any] = field(default_factory=dict)


class WorkflowGateway(Protocol):
    def collect(self, *, as_of: datetime, phase: str) -> WorkflowInputs: ...


class WorkflowRecorder(Protocol):
    def record(
        self,
        run: DecisionRun,
        raw_quotes: Mapping[str, Any],
    ) -> Path: ...


Ranker = Callable[
    [tuple[InstrumentContext, ...], DecisionConfig],
    tuple[list[Candidate], dict[str, list[str]]],
]
Allocator = Callable[
    [list[Candidate], list[Candidate], DecisionConfig],
    tuple[list[Allocation], list[str]],
]


class TailDecisionWorkflow:
    """Run one explicit phase using only injected I/O and strategy components."""

    def __init__(
        self,
        *,
        config: DecisionConfig,
        gateway: WorkflowGateway,
        etf_ranker: Ranker,
        stock_ranker: Ranker,
        allocator: Allocator,
        recorder: WorkflowRecorder | None = None,
    ) -> None:
        self.config = config
        self.gateway = gateway
        self.etf_ranker = etf_ranker
        self.stock_ranker = stock_ranker
        self.allocator = allocator
        self.recorder = recorder

    def run(self, *, as_of: str | datetime, phase: str) -> DecisionRun:
        instant = _parse_as_of(as_of)
        if phase not in _PHASES:
            raise ValueError(f"unsupported workflow phase: {phase}")
        run_id = f"{instant.strftime('%Y%m%dT%H%M%S')}_{phase}"

        try:
            inputs = self.gateway.collect(as_of=instant, phase=phase)
        except Exception as exc:
            return self._finish(
                _decision_run(
                    run_id=run_id,
                    as_of=instant,
                    status=DecisionStatus.BLOCKED,
                    reasons=(f"gateway_error:{type(exc).__name__}",),
                    config=self.config,
                ),
                raw_quotes={},
            )

        blocking_reasons = list(inputs.system_errors)
        all_instruments_blocked = bool(inputs.quality) and all(
            item.level is QualityLevel.BLOCKED for item in inputs.quality
        )
        if all_instruments_blocked:
            blocking_reasons.extend(
                reason
                for item in inputs.quality
                for reason in (item.reasons or ("quality_blocked",))
            )
        if blocking_reasons:
            return self._finish(
                _decision_run(
                    run_id=run_id,
                    as_of=instant,
                    status=DecisionStatus.BLOCKED,
                    quality=inputs.quality,
                    reasons=tuple(blocking_reasons),
                    config=self.config,
                ),
                raw_quotes=inputs.raw_quotes,
            )

        if phase not in {"preview", "final"}:
            return self._finish(
                _decision_run(
                    run_id=run_id,
                    as_of=instant,
                    status=DecisionStatus.NO_TRADE,
                    quality=inputs.quality,
                    reasons=(f"{phase}_completed",),
                    config=self.config,
                ),
                raw_quotes=inputs.raw_quotes,
            )

        try:
            etfs, rejected_etfs = self.etf_ranker(
                inputs.etf_contexts,
                self.config,
            )
            stocks, rejected_stocks = self.stock_ranker(
                inputs.stock_contexts,
                self.config,
            )
        except Exception as exc:
            return self._finish(
                _decision_run(
                    run_id=run_id,
                    as_of=instant,
                    status=DecisionStatus.BLOCKED,
                    quality=inputs.quality,
                    reasons=(f"strategy_error:{type(exc).__name__}",),
                    config=self.config,
                ),
                raw_quotes=inputs.raw_quotes,
            )

        strategy_reasons = _rejection_reasons(rejected_etfs, rejected_stocks)
        if any(item.level is QualityLevel.DEGRADED for item in inputs.quality):
            return self._finish(
                _decision_run(
                    run_id=run_id,
                    as_of=instant,
                    status=DecisionStatus.WATCH_ONLY,
                    quality=inputs.quality,
                    etfs=etfs,
                    stocks=stocks,
                    reasons=("degraded_quality", *strategy_reasons),
                    config=self.config,
                ),
                raw_quotes=inputs.raw_quotes,
            )

        if phase == "preview":
            status = (
                DecisionStatus.WATCH_ONLY
                if etfs or stocks
                else DecisionStatus.NO_TRADE
            )
            reason = "preview_only" if etfs or stocks else "no_qualifying_candidate"
            return self._finish(
                _decision_run(
                    run_id=run_id,
                    as_of=instant,
                    status=status,
                    quality=inputs.quality,
                    etfs=etfs,
                    stocks=stocks,
                    reasons=(reason, *strategy_reasons),
                    config=self.config,
                ),
                raw_quotes=inputs.raw_quotes,
            )

        allocations, allocation_reasons = self.allocator(etfs, stocks, self.config)
        status = (
            DecisionStatus.RECOMMENDED
            if allocations
            else DecisionStatus.NO_TRADE
        )
        reasons = (
            ("portfolio_allocated", *allocation_reasons, *strategy_reasons)
            if allocations
            else ("no_qualifying_candidate", *allocation_reasons, *strategy_reasons)
        )
        return self._finish(
            _decision_run(
                run_id=run_id,
                as_of=instant,
                status=status,
                quality=inputs.quality,
                etfs=etfs,
                stocks=stocks,
                allocations=allocations,
                reasons=reasons,
                config=self.config,
            ),
            raw_quotes=inputs.raw_quotes,
        )

    def _finish(
        self,
        run: DecisionRun,
        *,
        raw_quotes: Mapping[str, Any],
    ) -> DecisionRun:
        if self.recorder is not None:
            self.recorder.record(run, raw_quotes)
        return run


def _decision_run(
    *,
    run_id: str,
    as_of: datetime,
    status: DecisionStatus,
    config: DecisionConfig,
    quality: tuple[QualityDecision, ...] = (),
    etfs: list[Candidate] | tuple[Candidate, ...] = (),
    stocks: list[Candidate] | tuple[Candidate, ...] = (),
    allocations: list[Allocation] | tuple[Allocation, ...] = (),
    reasons: tuple[str, ...] = (),
) -> DecisionRun:
    return DecisionRun(
        run_id=run_id,
        as_of=as_of,
        status=status,
        quality=tuple(quality),
        etf_candidates=tuple(etfs),
        stock_candidates=tuple(stocks),
        allocations=tuple(allocations),
        reasons=tuple(reasons),
        strategy_version=config.strategy_version,
        config_hash=config_hash(config),
    )


def _rejection_reasons(
    *groups: dict[str, list[str]],
) -> tuple[str, ...]:
    return tuple(
        f"rejected:{instrument_id}:{reason}"
        for group in groups
        for instrument_id in sorted(group)
        for reason in group[instrument_id]
    )


def _parse_as_of(value: str | datetime) -> datetime:
    instant = datetime.fromisoformat(value) if isinstance(value, str) else value
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return instant
