"""Append-only audit artifacts for tail-decision runs."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
import json
import math
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
        if len(run.allocations) > 1:
            raise ValueError("tail-decision artifacts allow at most one allocation")

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
        primitive_quotes = _to_primitive(raw_quotes)
        payload["raw_quotes"] = primitive_quotes
        payload["audit"] = _audit_summary(run, primitive_quotes)
        _require_finite_numbers(payload)
        redacted = _redact(payload)
        json_text = json.dumps(
            redacted,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"

        _atomic_create(markdown_path, render_markdown(run, redacted["audit"]))
        _atomic_create(json_path, json_text)
        return json_path


def render_markdown(run: DecisionRun, audit: Mapping[str, Any] | None = None) -> str:
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
    audit = audit or _audit_summary(run, {})
    lines.extend(_audit_section(audit))
    lines.extend(["", "## Final Account Plan", ""])
    if run.allocations:
        item = run.allocations[0]
        lines.append(
            f"- Buy plan: `{item.instrument_id}` — {item.quantity} at no more than "
            f"{item.limit_price:.4f}; notional {item.notional:.2f}; "
            f"score {item.candidate_score:.2f}."
        )
    else:
        lines.append(f"- Non-actionable: `{run.status.value}`. Do not open a position.")
    lines.append("")
    return "\n".join(lines)


def _audit_section(audit: Mapping[str, Any]) -> list[str]:
    funnel = audit["funnel"]
    evidence = audit["evidence"]
    cash = audit["cash"]
    return [
        "",
        "## Audit Summary",
        "",
        "- Funnel: "
        f"research stocks {funnel['research_stocks']}; "
        f"observation stocks {funnel['observation_stocks']}; "
        f"research ETFs {funnel['research_etfs']}; "
        f"observation ETFs {funnel['observation_etfs']}; "
        f"finalists {funnel['finalists']}.",
        f"- Evidence source dates: {_join(tuple(evidence['source_dates']))}.",
        f"- Ignored evidence reason codes: {_join(tuple(evidence['reason_codes']))}.",
        "- Cash cap (configured / available / effective): "
        f"{_display_amount(cash['configured_position_cap_cny'])} / "
        f"{_display_amount(cash['available_cash_cny'])} / "
        f"{_display_amount(cash['effective_position_cap_cny'])}.",
    ]


def _join(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "none"


def _display_amount(value: object) -> str:
    return f"{value:.2f}" if isinstance(value, (int, float)) else "unknown"


def _audit_summary(run: DecisionRun, raw_quotes: Mapping[str, Any]) -> dict[str, Any]:
    funnel = raw_quotes.get("funnel_audit")
    funnel = funnel if isinstance(funnel, Mapping) else {}
    evidence = raw_quotes.get("research_evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    cash = raw_quotes.get("cash_audit")
    cash = cash if isinstance(cash, Mapping) else {}
    source_dates: set[str] = set()
    reason_codes: set[str] = set()
    for item in evidence.values():
        if not isinstance(item, Mapping):
            continue
        source_dates.update(_text_values(item.get("source_dates")))
        reason_codes.update(_text_values(item.get("reasons")))
    return {
        "funnel": {
            "base_stocks": _audit_count(funnel.get("base_stocks")),
            "research_stocks": _audit_count(funnel.get("research_stocks")),
            "observation_stocks": _audit_count(funnel.get("observation_stocks")),
            "research_etfs": _audit_count(funnel.get("research_etfs")),
            "observation_etfs": _audit_count(funnel.get("observation_etfs")),
            "finalists": len(run.etf_candidates) + len(run.stock_candidates),
            "allocations": len(run.allocations),
            "reasons": sorted(_text_values(funnel.get("reasons"))),
        },
        "evidence": {
            "source_dates": sorted(source_dates),
            "reason_codes": sorted(reason_codes),
        },
        "cash": {
            field: _audit_amount(cash.get(field))
            for field in (
                "configured_position_cap_cny",
                "available_cash_cny",
                "effective_position_cap_cny",
            )
        },
    }


def _audit_count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _audit_amount(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _text_values(value: object) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _require_finite_numbers(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("audit artifact contains a non-finite number")
    if isinstance(value, Mapping):
        for item in value.values():
            _require_finite_numbers(item)
    elif isinstance(value, (tuple, list, set)):
        for item in value:
            _require_finite_numbers(item)


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
