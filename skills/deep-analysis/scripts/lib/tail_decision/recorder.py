"""Append-only audit artifacts for tail-decision runs."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from .contracts import Candidate, DecisionRun


_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SECRET_PARTS = ("token", "secret", "password", "authorization")


class DecisionRecorder:
    """Persist one immutable JSON audit record and one human report per run."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def record(self, run: DecisionRun, raw_quotes: Mapping[str, Any]) -> Path:
        if not _SAFE_RUN_ID.fullmatch(run.run_id):
            raise ValueError("run_id contains unsafe filename characters")

        run_dir = (
            self.root
            / "reports"
            / "tail_decision"
            / run.as_of.strftime("%Y%m%d")
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        if any(run_dir.glob(f"*_{run.run_id}.json")):
            raise FileExistsError(f"run_id already recorded: {run.run_id}")

        stem = f"{run.as_of.strftime('%H%M%S%f')}_{run.run_id}"
        json_path = run_dir / f"{stem}.json"
        markdown_path = run_dir / f"{stem}.md"
        if json_path.exists() or markdown_path.exists():
            raise FileExistsError(f"run artifact already exists: {run.run_id}")

        payload = _to_primitive(run)
        payload["raw_quotes"] = _to_primitive(raw_quotes)
        redacted = _redact(payload)
        json_text = json.dumps(
            redacted,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"

        _atomic_create(markdown_path, render_markdown(run))
        _atomic_create(json_path, json_text)
        return json_path


def render_markdown(run: DecisionRun) -> str:
    """Render the decision into a compact report for manual execution."""

    lines = [
        f"# Tail Decision {run.run_id}",
        "",
        "## Status and Reasons",
        "",
        f"- Status: `{run.status.value}`",
        f"- As of: `{run.as_of.isoformat()}`",
        f"- Strategy: `{run.strategy_version}`",
        f"- Config hash: `{run.config_hash}`",
        f"- Reasons: {_join(run.reasons)}",
        "",
        "## Source Timestamps",
        "",
    ]
    source_lines = [
        f"- {quote.instrument_id} / {quote.source}: "
        f"quote `{quote.timestamp.isoformat()}`, fetched `{quote.fetched_at.isoformat()}`"
        for quality in run.quality
        for quote in quality.source_quotes
    ]
    lines.extend(source_lines or ["- No source quotes recorded."])
    lines.extend(_candidate_section("ETF Candidates", run.etf_candidates))
    lines.extend(_candidate_section("Stock Candidates", run.stock_candidates))
    lines.extend(["", "## Final Account Plan", ""])
    if run.allocations:
        lines.extend(
            f"- `{item.instrument_id}`: buy {item.quantity} at no more than "
            f"{item.limit_price:.4f}; notional {item.notional:.2f}; "
            f"score {item.candidate_score:.2f}."
            for item in run.allocations
        )
    else:
        lines.append("- No allocation. Do not open a position.")
    lines.append("")
    return "\n".join(lines)


def _candidate_section(title: str, candidates: tuple[Candidate, ...]) -> list[str]:
    lines = ["", f"## {title}", ""]
    if not candidates:
        lines.append("- None.")
        return lines
    for item in candidates:
        cancellation = item.exit_plan.get(
            "cancellation_rules",
            item.exit_plan.get("cancel_if", "none"),
        )
        exit_rule = item.exit_plan.get(
            "exit_session",
            item.exit_plan.get("exit", "not specified"),
        )
        lines.append(
            f"- `{item.instrument_id}` {item.name}: score {item.score:.2f}, "
            f"limit {item.max_buy_price:.4f}, lot {item.lot_size}, "
            f"theme `{item.theme}`; reasons: {_join(item.reasons)}; "
            f"cancellation: {cancellation}; exit: {exit_rule}."
        )
    return lines


def _join(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "none"


def _to_primitive(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _to_primitive(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _to_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_to_primitive(item) for item in value]
    return value


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized = key.casefold()
            if any(part in normalized for part in _SECRET_PARTS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _atomic_create(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.rename(path)
    finally:
        temporary_path.unlink(missing_ok=True)
