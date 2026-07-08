#!/usr/bin/env python3
"""Minimal Web UI wrapper for UZI-Skill.

This intentionally keeps the first web version small:
- submit one stock at a time
- choose lite / medium / deep
- run existing run.py in a background thread
- export generated artifacts to WEB_REPORTS_DIR
- list and open previous HTML reports
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[1]
RUN_PY = ROOT_DIR / "run.py"
DATA_DIR = Path(os.environ.get("UZI_WEB_DATA_DIR", ROOT_DIR / "data")).resolve()
REPORTS_DIR = Path(os.environ.get("UZI_WEB_REPORTS_DIR", ROOT_DIR / "web-reports")).resolve()
DEFAULT_DEPTH = os.environ.get("UZI_WEB_DEFAULT_DEPTH", "lite")
MAX_PARALLEL_JOBS = int(os.environ.get("UZI_WEB_MAX_PARALLEL_JOBS", "1"))
JOB_LOG_TAIL_CHARS = int(os.environ.get("UZI_WEB_JOB_LOG_TAIL_CHARS", "12000"))

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="UZI Web", version="0.1.0")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/reports", StaticFiles(directory=str(REPORTS_DIR), html=True), name="reports")


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=64)
    depth: Literal["lite", "medium", "deep"] = DEFAULT_DEPTH if DEFAULT_DEPTH in {"lite", "medium", "deep"} else "lite"
    no_resume: bool = False


@dataclass
class Job:
    id: str
    ticker: str
    depth: str
    status: str
    created_at: str
    updated_at: str
    command: list[str]
    report_url: str | None = None
    report_dir: str | None = None
    meta: dict | None = None
    returncode: int | None = None
    error: str | None = None
    log: str = ""


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_ticker_for_path(ticker: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", ticker.strip())
    return value[:48] or "stock"


def _active_jobs_count() -> int:
    return sum(1 for job in _jobs.values() if job.status in {"queued", "running"})


def _job_payload(job: Job) -> dict:
    payload = asdict(job)
    if len(payload.get("log") or "") > JOB_LOG_TAIL_CHARS:
        payload["log"] = payload["log"][-JOB_LOG_TAIL_CHARS:]
    return payload


def _read_report_meta(out_dir: Path) -> dict | None:
    meta_path = out_dir / "report.meta.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _run_job(job_id: str, out_dir: Path) -> None:
    with _lock:
        job = _jobs[job_id]
        job.status = "running"
        job.updated_at = _now()

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("UZI_CLI_ONLY", "1")

    try:
        proc = subprocess.Popen(
            job.command,
            cwd=str(ROOT_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert proc.stdout is not None
        chunks: list[str] = []
        for line in proc.stdout:
            chunks.append(line)
            with _lock:
                job = _jobs[job_id]
                job.log = (job.log + line)[-JOB_LOG_TAIL_CHARS:]
                job.updated_at = _now()
        returncode = proc.wait()
        full_log = "".join(chunks)

        meta = _read_report_meta(out_dir)
        index_path = out_dir / "index.html"
        report_url = f"/reports/{out_dir.name}/index.html" if index_path.exists() else None

        with _lock:
            job = _jobs[job_id]
            job.returncode = returncode
            job.meta = meta
            job.report_dir = str(out_dir)
            job.report_url = report_url
            job.log = full_log[-JOB_LOG_TAIL_CHARS:]
            job.status = "success" if returncode == 0 and report_url else "failed"
            if job.status == "failed":
                job.error = "analysis command failed or report index.html was not generated"
            job.updated_at = _now()
    except Exception as exc:
        with _lock:
            job = _jobs[job_id]
            job.status = "failed"
            job.error = str(exc)
            job.updated_at = _now()


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "run_py": str(RUN_PY),
        "reports_dir": str(REPORTS_DIR),
        "active_jobs": _active_jobs_count(),
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "default_depth": DEFAULT_DEPTH})


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest):
    ticker = payload.ticker.strip()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")
    if not RUN_PY.exists():
        raise HTTPException(status_code=500, detail=f"run.py not found: {RUN_PY}")

    with _lock:
        if _active_jobs_count() >= MAX_PARALLEL_JOBS:
            raise HTTPException(status_code=429, detail="another analysis job is still running")

    job_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_safe_ticker_for_path(ticker)}_{uuid.uuid4().hex[:8]}"
    out_dir = REPORTS_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(RUN_PY),
        ticker,
        "--depth",
        payload.depth,
        "--no-browser",
        "--output-dir",
        str(out_dir),
    ]
    if payload.no_resume:
        cmd.append("--no-resume")

    job = Job(
        id=job_id,
        ticker=ticker,
        depth=payload.depth,
        status="queued",
        created_at=_now(),
        updated_at=_now(),
        command=cmd,
    )
    with _lock:
        _jobs[job_id] = job

    thread = threading.Thread(target=_run_job, args=(job_id, out_dir), daemon=True)
    thread.start()
    return JSONResponse(_job_payload(job))


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    with _lock:
        jobs = sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [_job_payload(job) for job in jobs]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return _job_payload(job)


@app.get("/api/reports")
def list_reports() -> list[dict]:
    reports: list[dict] = []
    for report_dir in sorted(REPORTS_DIR.iterdir(), reverse=True):
        if not report_dir.is_dir():
            continue
        index_path = report_dir / "index.html"
        if not index_path.exists():
            continue
        meta = _read_report_meta(report_dir) or {}
        reports.append(
            {
                "id": report_dir.name,
                "url": f"/reports/{report_dir.name}/index.html",
                "ticker": meta.get("ticker") or report_dir.name,
                "depth": meta.get("depth"),
                "generated_at": meta.get("generated_at"),
                "one_liner": meta.get("one_liner"),
                "size_kb": meta.get("size_kb"),
            }
        )
    return reports
