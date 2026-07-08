"""Shared data models for UZI Web services."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Job:
    id: str
    ticker: str
    depth: str
    status: str
    created_at: str
    updated_at: str
    command: list[str]
    notify: bool = False
    source: str = "manual"
    batch_id: str | None = None
    report_url: str | None = None
    report_dir: str | None = None
    meta: dict | None = None
    returncode: int | None = None
    error: str | None = None
    log: str = ""

    def to_dict(self, log_tail_chars: int = 12000) -> dict:
        payload = asdict(self)
        log = payload.get("log") or ""
        if len(log) > log_tail_chars:
            payload["log"] = log[-log_tail_chars:]
        return payload
