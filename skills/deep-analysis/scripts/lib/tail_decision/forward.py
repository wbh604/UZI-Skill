"""Append-only forward validation observations and immutable release gates."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import DecisionRun, DecisionStatus
from .simulator import summarize_ledger


class ForwardJournal:
    def __init__(self, root: str | Path, *, account_assets: float = 10_000.0) -> None:
        if account_assets <= 0:
            raise ValueError("account_assets must be positive")
        self.root = Path(root)
        self.report_root = self.root / "reports" / "tail_decision" / "forward"
        self.records_path = self.report_root / "days.jsonl"
        self.account_assets = float(account_assets)

    def record_day(
        self,
        run: DecisionRun,
        ledger_events: Sequence[Mapping[str, object]],
        *,
        is_trading_day: bool,
    ) -> Path:
        records = self._records()
        if not any(record.get("run_id") == run.run_id for record in records):
            record = {
                "run_id": run.run_id,
                "as_of": run.as_of.isoformat(),
                "date": run.as_of.date().isoformat(),
                "phase": run.run_id.rsplit("_", 1)[-1],
                "status": run.status.value,
                "is_trading_day": bool(is_trading_day),
                "strategy_version": run.strategy_version,
                "config_hash": run.config_hash,
                "quality": [
                    {
                        "instrument_id": item.instrument_id,
                        "level": item.level.value,
                        "reasons": list(item.reasons),
                    }
                    for item in run.quality
                ],
                "allocations": [_primitive(item) for item in run.allocations],
                "ledger_events": [_primitive(dict(event)) for event in ledger_events],
            }
            self.report_root.mkdir(parents=True, exist_ok=True)
            with self.records_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                stream.flush()
                os.fsync(stream.fileno())
        self._write_latest()
        return self.records_path

    def summary(self) -> dict[str, object]:
        records = self._records()
        trading_dates = {
            str(record["date"])
            for record in records
            if record.get("is_trading_day") is True
        }
        events = [
            event
            for record in records
            for event in record.get("ledger_events", [])
            if isinstance(event, dict)
        ]
        paper_entries = [event for event in events if event.get("kind") == "paper_entry"]
        paper_exits = [event for event in events if event.get("kind") == "paper_exit"]
        metrics = summarize_ledger(paper_exits)
        maximum_drawdown_pct = (
            float(metrics["maximum_drawdown"]) / self.account_assets * 100.0
        )
        evidence_events = [
            event
            for event in events
            if event.get("kind") in {"paper_entry", "paper_exit"}
        ]
        snapshots_reconciled = bool(evidence_events) and all(
            bool(event.get("quote_sources")) for event in evidence_events
        )
        formal_start = next(
            (
                str(record["date"])
                for record in sorted(records, key=lambda item: str(item["as_of"]))
                if record.get("is_trading_day") is True
                and record.get("phase") == "final"
                and record.get("status") == DecisionStatus.RECOMMENDED.value
                and bool(record.get("allocations"))
                and bool(record.get("ledger_events"))
            ),
            None,
        )

        gates = {
            "minimum_trading_days": len(trading_dates) >= 60,
            "minimum_paper_entries": len(paper_entries) >= 40,
            "positive_net_pnl": float(metrics["net_pnl"]) > 0.0,
            "profit_factor": float(metrics["profit_factor"]) >= 1.2,
            "maximum_drawdown": maximum_drawdown_pct <= 8.0,
            "snapshots_reconciled": snapshots_reconciled,
            "formal_start_recorded": formal_start is not None,
        }
        release_state = "eligible" if all(gates.values()) else "collecting"
        return {
            "release_state": release_state,
            "formal_start_date": formal_start,
            "observations": len(records),
            "trading_days": len(trading_dates),
            "paper_entries": len(paper_entries),
            "paper_exits": len(paper_exits),
            "net_pnl": metrics["net_pnl"],
            "net_return_pct": metrics["net_return_pct"],
            "profit_factor": metrics["profit_factor"],
            "maximum_drawdown": metrics["maximum_drawdown"],
            "maximum_drawdown_pct": round(maximum_drawdown_pct, 6),
            "snapshots_reconciled": snapshots_reconciled,
            "by_instrument_type": metrics["by_instrument_type"],
            "gates": gates,
        }

    def _records(self) -> list[dict[str, object]]:
        if not self.records_path.is_file():
            return []
        records: list[dict[str, object]] = []
        with self.records_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid forward journal JSON at line {line_number}"
                    ) from exc
                records.append(record)
        return records

    def _write_latest(self) -> None:
        summary = self.summary()
        latest_json = self.report_root / "latest.json"
        latest_markdown = self.report_root / "latest.md"
        latest_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        latest_markdown.write_text(_render_markdown(summary), encoding="utf-8")


def _primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: _primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_primitive(item) for item in value]
    return value


def _render_markdown(summary: Mapping[str, object]) -> str:
    gates = summary["gates"]
    assert isinstance(gates, Mapping)
    lines = [
        "# Tail Decision Forward Validation",
        "",
        f"- Release state: `{summary['release_state']}`",
        f"- Formal start: `{summary['formal_start_date'] or 'not_started'}`",
        f"- Trading days: {summary['trading_days']} / 60",
        f"- Paper entries: {summary['paper_entries']} / 40",
        f"- Paper exits: {summary['paper_exits']}",
        f"- Net P&L: {summary['net_pnl']}",
        f"- Profit factor: {summary['profit_factor']}",
        f"- Maximum drawdown: {summary['maximum_drawdown_pct']}%",
        "",
        "## Gates",
        "",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in gates.items())
    lines.append("")
    return "\n".join(lines)
