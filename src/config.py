"""Centralized settings for UZI Web.

The module intentionally uses only environment variables so Docker Compose,
local CLI, and future Web configuration pages can share the same contract.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEPTHS = {"lite", "medium", "deep"}


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _csv(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.replace("，", ",").split(",") if item.strip()]


def _depth(name: str, default: str = "lite") -> str:
    value = os.getenv(name, default).strip().lower()
    return value if value in DEPTHS else default


@dataclass(frozen=True)
class Settings:
    root_dir: Path = ROOT_DIR
    run_py: Path = ROOT_DIR / "run.py"
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("UZI_WEB_DATA_DIR", ROOT_DIR / "data")).resolve())
    logs_dir: Path = field(default_factory=lambda: Path(os.getenv("UZI_WEB_LOGS_DIR", ROOT_DIR / "logs")).resolve())
    reports_dir: Path = field(default_factory=lambda: Path(os.getenv("UZI_WEB_REPORTS_DIR", ROOT_DIR / "reports")).resolve())

    web_host: str = os.getenv("UZI_WEB_HOST", "0.0.0.0")
    web_port: int = _int("UZI_WEB_PORT", 8977, minimum=1)
    public_base_url: str = os.getenv("UZI_WEB_PUBLIC_BASE_URL", "").rstrip("/")

    default_depth: str = _depth("UZI_WEB_DEFAULT_DEPTH", "lite")
    max_parallel_jobs: int = _int("UZI_WEB_MAX_PARALLEL_JOBS", 1, minimum=1)
    max_queue_size: int = _int("UZI_WEB_MAX_QUEUE_SIZE", 30, minimum=1)
    job_log_tail_chars: int = _int("UZI_WEB_JOB_LOG_TAIL_CHARS", 12000, minimum=1000)

    dingtalk_webhook_url: str = os.getenv("DINGTALK_WEBHOOK_URL", "").strip()
    dingtalk_secret: str = os.getenv("DINGTALK_SECRET", "").strip()
    dingtalk_notify_default: bool = _bool("UZI_DINGTALK_NOTIFY_DEFAULT", False)

    schedule_enabled: bool = _bool("UZI_SCHEDULE_ENABLED", False)
    schedule_times: list[str] = field(default_factory=lambda: _csv("UZI_SCHEDULE_TIMES"))
    schedule_tickers: list[str] = field(default_factory=lambda: _csv("UZI_SCHEDULE_TICKERS"))
    schedule_depth: str = _depth("UZI_SCHEDULE_DEPTH", _depth("UZI_WEB_DEFAULT_DEPTH", "lite"))
    schedule_notify: bool = _bool("UZI_SCHEDULE_NOTIFY", True)

    @property
    def job_reports_dir(self) -> Path:
        return self.reports_dir / "jobs"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.job_reports_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
