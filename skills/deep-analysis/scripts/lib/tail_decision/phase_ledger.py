"""Append-only paper position lifecycle for scheduled tail-decision phases."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Mapping

from .config import DecisionConfig
from .contracts import (
    Allocation,
    DecisionRun,
    QualityLevel,
)
from .simulator import simulate_entry, simulate_next_session_exit


EVENT_KINDS = frozenset(
    {
        "plan_created",
        "paper_entry",
        "paper_entry_unfilled",
        "exit_signal",
        "paper_exit",
        "paper_exit_blocked",
    }
)


class PhaseLedger:
    def __init__(
        self,
        root: str | Path,
        *,
        config: DecisionConfig | None = None,
    ) -> None:
        self.root = Path(root)
        self.path = self.root / "ledger" / "events.jsonl"
        self.config = config or DecisionConfig()

    def advance(
        self, *, phase: str, run: DecisionRun
    ) -> tuple[Mapping[str, object], ...]:
        handlers = {
            "final": self._record_plans,
            "close": self._record_entries,
            "exit_open": self._record_exit_signals,
            "exit_check": self._record_exits,
        }
        handler = handlers.get(phase)
        if handler is None:
            return ()
        return self._append(handler(run))

    def read_events(self) -> list[dict[str, object]]:
        if not self.path.is_file():
            return []
        events: list[dict[str, object]] = []
        with self.path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid ledger JSON at line {line_number}"
                    ) from exc
                if event.get("kind") not in EVENT_KINDS:
                    raise ValueError(f"invalid ledger event at line {line_number}")
                events.append(event)
        return events

    def current_positions(
        self, *, as_of: datetime
    ) -> dict[str, Mapping[str, object]]:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        positions: dict[str, Mapping[str, object]] = {}
        for event in self.read_events():
            occurred_at = datetime.fromisoformat(str(event["occurred_at"]))
            if occurred_at > as_of:
                continue
            instrument_id = str(event["instrument_id"])
            if event["kind"] == "paper_entry":
                positions[instrument_id] = event
            elif event["kind"] == "paper_exit":
                positions.pop(instrument_id, None)
        return positions

    def _record_plans(self, run: DecisionRun) -> list[dict[str, object]]:
        candidates = {
            item.instrument_id: item
            for item in (*run.etf_candidates, *run.stock_candidates)
        }
        events: list[dict[str, object]] = []
        for allocation in run.allocations:
            candidate = candidates.get(allocation.instrument_id)
            if candidate is None:
                raise ValueError("allocation has no matching candidate")
            events.append(
                self._base_event(run, "plan_created", allocation.instrument_id)
                | {
                    "instrument_type": candidate.instrument_type.value,
                    "quantity": allocation.quantity,
                    "planned_limit_price": allocation.limit_price,
                    "planned_notional": allocation.notional,
                    "candidate_score": allocation.candidate_score,
                    "exit_plan": dict(candidate.exit_plan),
                }
            )
        return events

    def _record_entries(self, run: DecisionRun) -> list[dict[str, object]]:
        events = self.read_events()
        terminal_entries = {
            str(event["instrument_id"])
            for event in events
            if event["kind"] in {"paper_entry", "paper_entry_unfilled"}
        }
        plans = [
            event
            for event in events
            if event["kind"] == "plan_created"
            and str(event["instrument_id"]) not in terminal_entries
        ]
        quality = {item.instrument_id: item for item in run.quality}
        created: list[dict[str, object]] = []
        for plan in plans:
            instrument_id = str(plan["instrument_id"])
            decision = quality.get(instrument_id)
            if (
                decision is None
                or decision.level is not QualityLevel.PASS
                or decision.canonical_quote is None
            ):
                created.append(
                    self._base_event(run, "paper_entry_unfilled", instrument_id)
                    | dict(plan)
                    | {
                        "event_id": self._event_id(
                            run.run_id, "paper_entry_unfilled", instrument_id
                        ),
                        "run_id": run.run_id,
                        "kind": "paper_entry_unfilled",
                        "occurred_at": run.as_of.isoformat(),
                        "block_reason": "quote_quality_below_pass",
                    }
                )
                continue

            allocation = _allocation_from_plan(plan)
            quote = decision.canonical_quote
            fill = simulate_entry(
                allocation,
                bar={
                    "timestamp": quote.timestamp,
                    "last_price": quote.last_price,
                    "volume": quote.volume,
                },
                instrument_type=str(plan["instrument_type"]),
                config=self.config,
            )
            kind = "paper_entry" if fill.get("filled") else "paper_entry_unfilled"
            payload = (
                self._base_event(run, kind, instrument_id)
                | dict(plan)
                | dict(fill)
                | {
                    "event_id": self._event_id(run.run_id, kind, instrument_id),
                    "run_id": run.run_id,
                    "kind": kind,
                    "occurred_at": run.as_of.isoformat(),
                    "quote_sources": _source_timestamps(decision.source_quotes),
                }
            )
            if not fill.get("filled"):
                payload["block_reason"] = fill.get("reason", "entry_unfilled")
            created.append(payload)
        return created

    def _record_exit_signals(self, run: DecisionRun) -> list[dict[str, object]]:
        return [
            self._base_event(run, "exit_signal", instrument_id)
            | {
                "instrument_type": position["instrument_type"],
                "entry_date": position["entry_date"],
                "entry_price": position["entry_price"],
            }
            for instrument_id, position in self.current_positions(
                as_of=run.as_of
            ).items()
        ]

    def _record_exits(self, run: DecisionRun) -> list[dict[str, object]]:
        quality = {item.instrument_id: item for item in run.quality}
        created: list[dict[str, object]] = []
        for instrument_id, position in self.current_positions(
            as_of=run.as_of
        ).items():
            decision = quality.get(instrument_id)
            if (
                decision is None
                or decision.level is not QualityLevel.PASS
                or decision.canonical_quote is None
            ):
                created.append(
                    self._base_event(run, "paper_exit_blocked", instrument_id)
                    | {
                        "instrument_type": position["instrument_type"],
                        "block_reason": "quote_quality_below_pass",
                    }
                )
                continue

            quote = decision.canonical_quote
            result = simulate_next_session_exit(
                position,
                bar={
                    "timestamp": quote.timestamp,
                    "last_price": quote.last_price,
                    "volume": quote.volume,
                },
                instrument_type=str(position["instrument_type"]),
                config=self.config,
            )
            kind = "paper_exit" if result.get("filled") else "paper_exit_blocked"
            payload = (
                self._base_event(run, kind, instrument_id)
                | dict(result)
                | {
                    "event_id": self._event_id(run.run_id, kind, instrument_id),
                    "run_id": run.run_id,
                    "kind": kind,
                    "occurred_at": run.as_of.isoformat(),
                    "quote_sources": _source_timestamps(decision.source_quotes),
                }
            )
            if not result.get("filled"):
                payload["block_reason"] = result.get("reason", "exit_blocked")
            created.append(payload)
        return created

    def _base_event(
        self, run: DecisionRun, kind: str, instrument_id: str
    ) -> dict[str, object]:
        return {
            "event_id": self._event_id(run.run_id, kind, instrument_id),
            "run_id": run.run_id,
            "kind": kind,
            "instrument_id": instrument_id,
            "occurred_at": run.as_of.isoformat(),
            "strategy_version": run.strategy_version,
            "config_hash": run.config_hash,
        }

    @staticmethod
    def _event_id(run_id: str, kind: str, instrument_id: str) -> str:
        return f"{run_id}|{kind}|{instrument_id}"

    def _append(
        self, candidates: list[dict[str, object]]
    ) -> tuple[Mapping[str, object], ...]:
        existing = {str(event["event_id"]) for event in self.read_events()}
        additions = [
            event for event in candidates if str(event["event_id"]) not in existing
        ]
        if not additions:
            return ()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            for event in additions:
                stream.write(
                    json.dumps(
                        event,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
            stream.flush()
            os.fsync(stream.fileno())
        return tuple(additions)


def _allocation_from_plan(plan: Mapping[str, object]) -> Allocation:
    return Allocation(
        instrument_id=str(plan["instrument_id"]),
        quantity=int(plan["quantity"]),
        limit_price=float(plan["planned_limit_price"]),
        notional=float(plan["planned_notional"]),
        candidate_score=float(plan["candidate_score"]),
    )


def _source_timestamps(quotes) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "source": quote.source,
            "timestamp": quote.timestamp.isoformat(),
            "fetched_at": quote.fetched_at.isoformat(),
        }
        for quote in quotes
    )
