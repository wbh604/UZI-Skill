"""Read-only adapters for optional AI discovery and UZI research evidence."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
import json
import math
from pathlib import Path
import re


_INSTRUMENT_ID = re.compile(r"^(?P<code>\d{6})\.(?P<exchange>SH|SZ)$")
_PREFIXED_INSTRUMENT_ID = re.compile(r"^(?P<exchange>SH|SZ)\.?((?P<code>\d{6}))$")


@dataclass(frozen=True)
class ResearchEvidence:
    """Non-actionable research signals associated with one instrument."""

    instrument_id: str
    ai_score: float | None = None
    uzi_score: float | None = None
    uzi_coverage: float | None = None
    uzi_state: str = "unavailable"
    source_dates: tuple[str, ...] = ()
    source_paths: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "instrument_id", canonical_instrument_id(self.instrument_id))
        object.__setattr__(self, "source_dates", tuple(self.source_dates))
        object.__setattr__(self, "source_paths", tuple(self.source_paths))
        object.__setattr__(self, "reasons", tuple(self.reasons))


def canonical_instrument_id(value: object) -> str:
    """Return the canonical six-digit Shanghai or Shenzhen identifier."""

    if not isinstance(value, str):
        raise ValueError("instrument id must be a string")
    normalized = value.strip().upper()
    match = _INSTRUMENT_ID.fullmatch(normalized) or _PREFIXED_INSTRUMENT_ID.fullmatch(normalized)
    if match is None:
        raise ValueError(f"invalid instrument id: {value!r}")
    return f"{match.group('code')}.{match.group('exchange')}"


def load_ai_discovery(
    root: Path,
    as_of: date,
    max_age_days: int = 10,
) -> dict[str, ResearchEvidence]:
    """Load recent weekly AI hints without deriving any trading action."""

    if max_age_days < 0:
        raise ValueError("max_age_days must be non-negative")
    collected: list[ResearchEvidence] = []
    try:
        paths = sorted(Path(root).glob("weekly_candidates_*.json"))
    except OSError:
        return {}
    for path in paths:
        payload = _read_json(path)
        if not isinstance(payload, dict):
            continue
        source_date = _parse_date(payload.get("as_of"))
        if source_date is None or not _is_fresh_date(source_date, as_of, max_age_days):
            continue
        for entry in _discovery_entries(payload):
            evidence = _ai_evidence(entry, source_date, path)
            if evidence is not None:
                collected.append(evidence)
    return merge_research_evidence(
        *({item.instrument_id: item} for item in collected)
    )


def load_uzi_evidence(
    cache_root: Path,
    instrument_ids: Iterable[str],
    as_of: datetime,
    max_age_days: int = 10,
) -> dict[str, ResearchEvidence]:
    """Load UZI cache evidence, degrading unavailable inputs per instrument."""

    if max_age_days < 0:
        raise ValueError("max_age_days must be non-negative")
    requested = _requested_ids(instrument_ids)
    result = {
        instrument_id: ResearchEvidence(
            instrument_id, reasons=("uzi_missing",)
        )
        for instrument_id in requested
    }
    try:
        directories = sorted(path for path in Path(cache_root).iterdir() if path.is_dir())
    except OSError:
        return result
    for directory in directories:
        try:
            directory_id = canonical_instrument_id(directory.name)
        except ValueError:
            continue
        if directory_id not in result:
            continue
        source = directory / "synthesis.json"
        if not source.is_file():
            continue
        source_date = _mtime_date(source, as_of)
        if source_date is None:
            result[directory_id] = _unavailable(directory_id, "uzi_unreadable")
            continue
        if not _is_fresh_date(source_date, as_of.date(), max_age_days):
            result[directory_id] = _unavailable(directory_id, "uzi_stale", source, source_date)
            continue
        payload = _read_json(source)
        if not isinstance(payload, dict):
            result[directory_id] = _unavailable(directory_id, "uzi_invalid_json", source, source_date)
            continue
        try:
            ticker = canonical_instrument_id(payload.get("ticker"))
        except ValueError:
            result[directory_id] = _unavailable(directory_id, "uzi_invalid_ticker", source, source_date)
            continue
        if ticker != directory_id:
            result[directory_id] = _unavailable(directory_id, "uzi_code_mismatch", source, source_date)
            continue
        result[directory_id] = _uzi_evidence(directory_id, payload, source, source_date)
    return result


def merge_research_evidence(
    *groups: Mapping[str, ResearchEvidence],
) -> dict[str, ResearchEvidence]:
    """Merge optional evidence while retaining any explicit UZI block."""

    grouped: dict[str, list[ResearchEvidence]] = {}
    for group in groups:
        for instrument_id, evidence in group.items():
            if not isinstance(evidence, ResearchEvidence):
                continue
            try:
                canonical = canonical_instrument_id(instrument_id)
            except ValueError:
                continue
            grouped.setdefault(canonical, []).append(evidence)
    return {
        instrument_id: _merge_one(instrument_id, values)
        for instrument_id, values in grouped.items()
    }


def _discovery_entries(payload: dict) -> Iterable[dict]:
    for field in ("candidates", "review_queue"):
        entries = payload.get(field, [])
        if isinstance(entries, list):
            yield from (entry for entry in entries if isinstance(entry, dict))


def _ai_evidence(entry: dict, source_date: date, path: Path) -> ResearchEvidence | None:
    try:
        instrument_id = canonical_instrument_id(entry.get("code", entry.get("ticker")))
    except ValueError:
        return None
    ai_score = _score(entry.get("score"))
    uzi = entry.get("uzi") if isinstance(entry.get("uzi"), dict) else {}
    uzi_score = _score(uzi.get("score"))
    coverage = _coverage(uzi.get("data_coverage"))
    decision = entry.get("uzi_decision") if isinstance(entry.get("uzi_decision"), dict) else {}
    state = _state(decision.get("state"), has_evidence=uzi_score is not None)
    if ai_score is None and uzi_score is None:
        return None
    return ResearchEvidence(
        instrument_id=instrument_id,
        ai_score=ai_score,
        uzi_score=uzi_score,
        uzi_coverage=coverage,
        uzi_state=state,
        source_dates=(source_date.isoformat(),),
        source_paths=(str(path),),
    )


def _uzi_evidence(
    instrument_id: str, payload: dict, source: Path, source_date: date
) -> ResearchEvidence:
    score = _score(payload.get("overall_score"))
    coverage = _coverage(payload.get("data_coverage"))
    if score is None or coverage is None:
        return _unavailable(instrument_id, "uzi_invalid_payload", source, source_date)
    state = _state(payload.get("uzi_decision_state"), has_evidence=True)
    reasons = ("uzi_blocked",) if state == "blocked" else ()
    return ResearchEvidence(
        instrument_id=instrument_id,
        uzi_score=score,
        uzi_coverage=coverage,
        uzi_state=state,
        source_dates=(source_date.isoformat(),),
        source_paths=(str(source),),
        reasons=reasons,
    )


def _unavailable(
    instrument_id: str, reason: str, source: Path | None = None,
    source_date: date | None = None,
) -> ResearchEvidence:
    return ResearchEvidence(
        instrument_id,
        source_dates=(source_date.isoformat(),) if source_date else (),
        source_paths=(str(source),) if source else (),
        reasons=(reason,),
    )


def _merge_one(instrument_id: str, values: list[ResearchEvidence]) -> ResearchEvidence:
    def first(field: str) -> float | None:
        return next((getattr(item, field) for item in values if getattr(item, field) is not None), None)

    states = {item.uzi_state for item in values}
    state = "blocked" if "blocked" in states else "approved" if "approved" in states else "unavailable"
    return ResearchEvidence(
        instrument_id=instrument_id,
        ai_score=first("ai_score"),
        uzi_score=first("uzi_score"),
        uzi_coverage=first("uzi_coverage"),
        uzi_state=state,
        source_dates=_unique(item.source_dates for item in values),
        source_paths=_unique(item.source_paths for item in values),
        reasons=_unique(item.reasons for item in values),
    )


def _unique(groups: Iterable[Iterable[str]]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for group in groups for value in group))


def _requested_ids(instrument_ids: Iterable[str]) -> tuple[str, ...]:
    requested: list[str] = []
    for value in instrument_ids:
        try:
            instrument_id = canonical_instrument_id(value)
        except ValueError:
            continue
        if instrument_id not in requested:
            requested.append(instrument_id)
    return tuple(requested)


def _read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _mtime_date(path: Path, as_of: datetime) -> date | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=as_of.tzinfo).date()
    except OSError:
        return None


def _is_fresh_date(source_date: date, as_of: date, max_age_days: int) -> bool:
    age_days = (as_of - source_date).days
    return 0 <= age_days <= max_age_days


def _score(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if math.isfinite(score) and 0.0 <= score <= 100.0 else None


def _coverage(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        coverage = float(value)
    except (TypeError, ValueError):
        return None
    return coverage if math.isfinite(coverage) and 0.0 <= coverage <= 1.0 else None


def _state(value: object, *, has_evidence: bool) -> str:
    if value == "blocked":
        return "blocked"
    if value == "approved" or has_evidence:
        return "approved"
    return "unavailable"
