"""In-memory job queue for UZI Web.

The queue is intentionally simple and low-concurrency because UZI report
generation is CPU/network heavy and uses shared cache directories.
"""
from __future__ import annotations

import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from src.config import DEPTHS, Settings
from src.services.dingtalk_notifier import DingTalkNotifier
from src.services.models import Job
from src.services.uzi_runner import UziRunner

logger = logging.getLogger(__name__)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_tickers(text: str) -> list[str]:
    raw = re.split(r"[\s,，;；]+", text.strip())
    seen: set[str] = set()
    tickers: list[str] = []
    for item in raw:
        ticker = item.strip()
        if not ticker:
            continue
        key = ticker.upper()
        if key in seen:
            continue
        seen.add(key)
        tickers.append(ticker)
    return tickers


def safe_ticker_for_path(ticker: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", ticker.strip())
    return value[:48] or "stock"


class JobQueue:
    def __init__(self, settings: Settings, runner: UziRunner, notifier: DingTalkNotifier) -> None:
        self.settings = settings
        self.runner = runner
        self.notifier = notifier
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(settings.max_parallel_jobs)

    def active_jobs_count(self) -> int:
        return sum(1 for job in self._jobs.values() if job.status in {"queued", "running"})

    def submit(
        self,
        ticker: str,
        depth: str,
        no_resume: bool = False,
        notify: bool | None = None,
        source: str = "manual",
        batch_id: str | None = None,
    ) -> Job:
        ticker = ticker.strip()
        if not ticker:
            raise HTTPException(status_code=400, detail="ticker is required")
        if depth not in DEPTHS:
            raise HTTPException(status_code=400, detail=f"invalid depth: {depth}")
        if not self.settings.run_py.exists():
            raise HTTPException(status_code=500, detail=f"run.py not found: {self.settings.run_py}")

        with self._lock:
            if self.active_jobs_count() >= self.settings.max_queue_size:
                raise HTTPException(status_code=429, detail="job queue is full")

        job_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_ticker_for_path(ticker)}_{uuid.uuid4().hex[:8]}"
        out_dir = self.settings.job_reports_dir / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        command = self.runner.build_command(ticker, depth, out_dir, no_resume=no_resume)

        job = Job(
            id=job_id,
            ticker=ticker,
            depth=depth,
            status="queued",
            created_at=now_utc(),
            updated_at=now_utc(),
            command=command,
            notify=self.settings.dingtalk_notify_default if notify is None else notify,
            source=source,
            batch_id=batch_id,
        )
        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(target=self._run_job, args=(job_id, out_dir), daemon=True)
        thread.start()
        return job

    def submit_batch(
        self,
        tickers: list[str],
        depth: str,
        no_resume: bool = False,
        notify: bool | None = None,
        source: str = "batch",
    ) -> tuple[str, list[Job]]:
        batch_id = f"{source}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        jobs = [
            self.submit(
                ticker=ticker,
                depth=depth,
                no_resume=no_resume,
                notify=notify,
                source=source,
                batch_id=batch_id,
            )
            for ticker in tickers
        ]
        return batch_id, jobs

    def _append_log(self, job_id: str, text: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.log = (job.log + text)[-self.settings.job_log_tail_chars :]
            job.updated_at = now_utc()

    def _run_job(self, job_id: str, out_dir: Path) -> None:
        acquired = False
        try:
            self._semaphore.acquire()
            acquired = True
            with self._lock:
                job = self._jobs[job_id]
                job.status = "running"
                job.updated_at = now_utc()

            logger.info("UZI job started: id=%s ticker=%s depth=%s", job.id, job.ticker, job.depth)
            returncode, full_log = self.runner.run(job, out_dir, on_log=lambda line: self._append_log(job_id, line))
            meta = self.runner.read_report_meta(out_dir)
            index_path = out_dir / "index.html"
            report_url = f"/reports/jobs/{out_dir.name}/index.html" if index_path.exists() else None

            with self._lock:
                job = self._jobs[job_id]
                job.returncode = returncode
                job.meta = meta
                job.report_dir = str(out_dir)
                job.report_url = report_url
                job.log = full_log[-self.settings.job_log_tail_chars :]
                job.status = "success" if returncode == 0 and report_url else "failed"
                if job.status == "failed":
                    job.error = "analysis command failed or report index.html was not generated"
                job.updated_at = now_utc()
            logger.info("UZI job finished: id=%s status=%s", job_id, self._jobs[job_id].status)
        except Exception as exc:
            logger.exception("UZI job failed: id=%s", job_id)
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                job.error = str(exc)
                job.updated_at = now_utc()
        finally:
            if acquired:
                self._semaphore.release()
            self._notify_job_finished(job_id)

    def _notify_job_finished(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job or not job.notify:
            return
        ok, message = self.notifier.notify_job_finished(job)
        self._append_log(job_id, f"\n[DingTalk] {message}\n")
        if not ok:
            logger.warning("DingTalk notify failed for job %s: %s", job_id, message)

    def list_jobs(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_reports(self) -> list[dict]:
        reports: list[dict] = []
        for report_dir in sorted(self.settings.job_reports_dir.iterdir(), reverse=True):
            if not report_dir.is_dir():
                continue
            index_path = report_dir / "index.html"
            if not index_path.exists():
                continue
            meta = self.runner.read_report_meta(report_dir) or {}
            relative_url = f"/reports/jobs/{report_dir.name}/index.html"
            absolute_url = self.notifier.absolute_report_url(relative_url)
            reports.append(
                {
                    "id": report_dir.name,
                    "url": relative_url,
                    "absolute_url": absolute_url,
                    "ticker": meta.get("ticker") or report_dir.name,
                    "depth": meta.get("depth"),
                    "generated_at": meta.get("generated_at"),
                    "one_liner": meta.get("one_liner"),
                    "size_kb": meta.get("size_kb"),
                }
            )
        return reports
