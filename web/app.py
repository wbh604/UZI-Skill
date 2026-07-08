#!/usr/bin/env python3
"""Minimal Web UI wrapper for UZI-Skill.

This Web wrapper keeps the core UZI workflow unchanged:
- submit one stock or a small batch from the browser
- choose lite / medium / deep
- run existing run.py in background worker threads
- export generated artifacts to WEB_REPORTS_DIR
- list and open previous HTML reports
- optionally send DingTalk notifications
- optionally run a simple env-driven daily schedule
"""
from __future__ import annotations

import base64
import hashlib
import hmac
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
from urllib.parse import quote_plus

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[1]
RUN_PY = ROOT_DIR / "run.py"
DATA_DIR = Path(os.environ.get("UZI_WEB_DATA_DIR", ROOT_DIR / "data")).resolve()
REPORTS_DIR = Path(os.environ.get("UZI_WEB_REPORTS_DIR", ROOT_DIR / "web-reports")).resolve()

DEPTHS = {"lite", "medium", "deep"}
Depth = Literal["lite", "medium", "deep"]

DEFAULT_DEPTH = os.environ.get("UZI_WEB_DEFAULT_DEPTH", "lite")
if DEFAULT_DEPTH not in DEPTHS:
    DEFAULT_DEPTH = "lite"

MAX_PARALLEL_JOBS = max(1, int(os.environ.get("UZI_WEB_MAX_PARALLEL_JOBS", "1")))
MAX_QUEUE_SIZE = max(MAX_PARALLEL_JOBS, int(os.environ.get("UZI_WEB_MAX_QUEUE_SIZE", "30")))
JOB_LOG_TAIL_CHARS = int(os.environ.get("UZI_WEB_JOB_LOG_TAIL_CHARS", "12000"))
PUBLIC_BASE_URL = os.environ.get("UZI_WEB_PUBLIC_BASE_URL", "").rstrip("/")

DINGTALK_WEBHOOK_URL = os.environ.get("DINGTALK_WEBHOOK_URL", "").strip()
DINGTALK_SECRET = os.environ.get("DINGTALK_SECRET", "").strip()
DEFAULT_NOTIFY_ENABLED = os.environ.get("UZI_DINGTALK_NOTIFY_DEFAULT", "false").lower() in {"1", "true", "yes", "on"}

SCHEDULE_ENABLED = os.environ.get("UZI_SCHEDULE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
SCHEDULE_TIMES_RAW = os.environ.get("UZI_SCHEDULE_TIMES", "")
SCHEDULE_TICKERS_RAW = os.environ.get("UZI_SCHEDULE_TICKERS", "")
SCHEDULE_DEPTH = os.environ.get("UZI_SCHEDULE_DEPTH", DEFAULT_DEPTH)
if SCHEDULE_DEPTH not in DEPTHS:
    SCHEDULE_DEPTH = DEFAULT_DEPTH
SCHEDULE_NOTIFY = os.environ.get("UZI_SCHEDULE_NOTIFY", "true").lower() in {"1", "true", "yes", "on"}

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="UZI Web", version="0.2.0")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/reports", StaticFiles(directory=str(REPORTS_DIR), html=True), name="reports")


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=64)
    depth: Depth = DEFAULT_DEPTH  # type: ignore[assignment]
    no_resume: bool = False
    notify: bool = DEFAULT_NOTIFY_ENABLED


class BatchAnalyzeRequest(BaseModel):
    tickers: str = Field(..., min_length=1, max_length=4000)
    depth: Depth = DEFAULT_DEPTH  # type: ignore[assignment]
    no_resume: bool = False
    notify: bool = DEFAULT_NOTIFY_ENABLED


class DingTalkTestRequest(BaseModel):
    content: str = "股票：这是一条来自 UZI Web 的钉钉测试消息。"


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


_jobs: dict[str, Job] = {}
_lock = threading.Lock()
_job_semaphore = threading.BoundedSemaphore(MAX_PARALLEL_JOBS)
_last_schedule_key: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_ticker_for_path(ticker: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", ticker.strip())
    return value[:48] or "stock"


def _parse_tickers(text: str) -> list[str]:
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


def _absolute_report_url(relative_url: str | None) -> str | None:
    if not relative_url:
        return None
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL}{relative_url}"
    return relative_url


def _dingtalk_signed_url() -> str:
    if not DINGTALK_SECRET:
        return DINGTALK_WEBHOOK_URL
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{DINGTALK_SECRET}"
    digest = hmac.new(
        DINGTALK_SECRET.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    sign = quote_plus(base64.b64encode(digest).decode("utf-8"))
    separator = "&" if "?" in DINGTALK_WEBHOOK_URL else "?"
    return f"{DINGTALK_WEBHOOK_URL}{separator}timestamp={timestamp}&sign={sign}"


def _send_dingtalk_text(content: str) -> tuple[bool, str]:
    if not DINGTALK_WEBHOOK_URL:
        return False, "DINGTALK_WEBHOOK_URL is not configured"

    # Keep the keyword at the beginning for DingTalk robots using keyword security.
    if "股票" not in content:
        content = f"股票：{content}"

    try:
        resp = requests.post(
            _dingtalk_signed_url(),
            json={"msgtype": "text", "text": {"content": content}},
            timeout=12,
        )
    except Exception as exc:
        return False, f"request failed: {exc}"

    try:
        data = resp.json()
    except Exception:
        data = {"errmsg": resp.text[:300]}

    if resp.status_code >= 400:
        return False, f"HTTP {resp.status_code}: {data}"

    errcode = data.get("errcode")
    if errcode not in (0, None):
        return False, f"DingTalk errcode={errcode}, errmsg={data.get('errmsg')}"
    return True, data.get("errmsg") or "ok"


def _format_job_notification(job: Job) -> str:
    ok = job.status == "success"
    status_text = "成功" if ok else "失败"
    lines = [
        f"股票 UZI 报告任务{status_text}",
        f"标的：{job.ticker}",
        f"深度：{job.depth}",
        f"来源：{job.source}",
    ]
    if job.report_url:
        lines.append(f"报告：{_absolute_report_url(job.report_url)}")
    if job.meta and job.meta.get("one_liner"):
        lines.append(f"摘要：{job.meta.get('one_liner')}")
    if job.error:
        lines.append(f"错误：{job.error}")
    lines.append(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


def _notify_job_finished(job_id: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job or not job.notify:
            return
        payload = _format_job_notification(job)
    ok, message = _send_dingtalk_text(payload)
    with _lock:
        job = _jobs.get(job_id)
        if job:
            job.log = (job.log + f"\n[DingTalk] {message}\n")[-JOB_LOG_TAIL_CHARS:]
            if not ok and not job.error:
                job.error = f"DingTalk notify failed: {message}"
            job.updated_at = _now()


def _run_job(job_id: str, out_dir: Path) -> None:
    acquired = False
    try:
        _job_semaphore.acquire()
        acquired = True
        with _lock:
            job = _jobs[job_id]
            job.status = "running"
            job.updated_at = _now()

        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("UZI_CLI_ONLY", "1")

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
    finally:
        if acquired:
            _job_semaphore.release()
        _notify_job_finished(job_id)


def _submit_job(
    ticker: str,
    depth: str,
    no_resume: bool = False,
    notify: bool = DEFAULT_NOTIFY_ENABLED,
    source: str = "manual",
    batch_id: str | None = None,
) -> Job:
    ticker = ticker.strip()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")
    if depth not in DEPTHS:
        raise HTTPException(status_code=400, detail=f"invalid depth: {depth}")
    if not RUN_PY.exists():
        raise HTTPException(status_code=500, detail=f"run.py not found: {RUN_PY}")

    with _lock:
        if _active_jobs_count() >= MAX_QUEUE_SIZE:
            raise HTTPException(status_code=429, detail="job queue is full")

    job_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_safe_ticker_for_path(ticker)}_{uuid.uuid4().hex[:8]}"
    out_dir = REPORTS_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(RUN_PY),
        ticker,
        "--depth",
        depth,
        "--no-browser",
        "--output-dir",
        str(out_dir),
    ]
    if no_resume:
        cmd.append("--no-resume")

    job = Job(
        id=job_id,
        ticker=ticker,
        depth=depth,
        status="queued",
        created_at=_now(),
        updated_at=_now(),
        command=cmd,
        notify=notify,
        source=source,
        batch_id=batch_id,
    )
    with _lock:
        _jobs[job_id] = job

    thread = threading.Thread(target=_run_job, args=(job_id, out_dir), daemon=True)
    thread.start()
    return job


def _configured_schedule_times() -> list[str]:
    times = []
    for item in re.split(r"[\s,，;；]+", SCHEDULE_TIMES_RAW.strip()):
        if re.fullmatch(r"\d{2}:\d{2}", item):
            times.append(item)
    return times


def _scheduler_loop() -> None:
    global _last_schedule_key
    while True:
        time.sleep(20)
        if not SCHEDULE_ENABLED:
            continue
        schedule_times = _configured_schedule_times()
        tickers = _parse_tickers(SCHEDULE_TICKERS_RAW)
        if not schedule_times or not tickers:
            continue

        now = datetime.now()
        current = now.strftime("%H:%M")
        if current not in schedule_times:
            continue

        schedule_key = f"{now.strftime('%Y-%m-%d')} {current}"
        if _last_schedule_key == schedule_key:
            continue
        _last_schedule_key = schedule_key

        batch_id = f"schedule_{now.strftime('%Y%m%d_%H%M')}_{uuid.uuid4().hex[:6]}"
        submitted = 0
        for ticker in tickers:
            try:
                _submit_job(
                    ticker=ticker,
                    depth=SCHEDULE_DEPTH,
                    no_resume=False,
                    notify=SCHEDULE_NOTIFY,
                    source="schedule",
                    batch_id=batch_id,
                )
                submitted += 1
            except Exception:
                # Do not stop the scheduler because one ticker failed to queue.
                continue

        if submitted and SCHEDULE_NOTIFY:
            _send_dingtalk_text(
                f"股票 UZI 定时任务已提交\n批次：{batch_id}\n数量：{submitted}\n深度：{SCHEDULE_DEPTH}\n时间：{schedule_key}"
            )


@app.on_event("startup")
def _start_scheduler() -> None:
    if SCHEDULE_ENABLED:
        thread = threading.Thread(target=_scheduler_loop, daemon=True)
        thread.start()


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "run_py": str(RUN_PY),
        "reports_dir": str(REPORTS_DIR),
        "active_jobs": _active_jobs_count(),
        "max_parallel_jobs": MAX_PARALLEL_JOBS,
        "dingtalk_configured": bool(DINGTALK_WEBHOOK_URL),
        "schedule_enabled": SCHEDULE_ENABLED,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "default_depth": DEFAULT_DEPTH,
            "default_notify": DEFAULT_NOTIFY_ENABLED,
        },
    )


@app.get("/api/config")
def get_config() -> dict:
    return {
        "default_depth": DEFAULT_DEPTH,
        "max_parallel_jobs": MAX_PARALLEL_JOBS,
        "max_queue_size": MAX_QUEUE_SIZE,
        "dingtalk_configured": bool(DINGTALK_WEBHOOK_URL),
        "dingtalk_secret_configured": bool(DINGTALK_SECRET),
        "default_notify": DEFAULT_NOTIFY_ENABLED,
        "public_base_url": PUBLIC_BASE_URL,
        "schedule": {
            "enabled": SCHEDULE_ENABLED,
            "times": _configured_schedule_times(),
            "tickers": _parse_tickers(SCHEDULE_TICKERS_RAW),
            "depth": SCHEDULE_DEPTH,
            "notify": SCHEDULE_NOTIFY,
        },
    }


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest):
    job = _submit_job(
        ticker=payload.ticker,
        depth=payload.depth,
        no_resume=payload.no_resume,
        notify=payload.notify,
        source="manual",
    )
    return JSONResponse(_job_payload(job))


@app.post("/api/analyze/batch")
def analyze_batch(payload: BatchAnalyzeRequest):
    tickers = _parse_tickers(payload.tickers)
    if not tickers:
        raise HTTPException(status_code=400, detail="no valid tickers found")
    if len(tickers) > 50:
        raise HTTPException(status_code=400, detail="batch size is limited to 50 tickers")

    batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    jobs: list[dict] = []
    for ticker in tickers:
        job = _submit_job(
            ticker=ticker,
            depth=payload.depth,
            no_resume=payload.no_resume,
            notify=payload.notify,
            source="batch",
            batch_id=batch_id,
        )
        jobs.append(_job_payload(job))

    if payload.notify and DINGTALK_WEBHOOK_URL:
        _send_dingtalk_text(
            f"股票 UZI 批量任务已提交\n批次：{batch_id}\n数量：{len(jobs)}\n深度：{payload.depth}"
        )

    return {"batch_id": batch_id, "count": len(jobs), "jobs": jobs}


@app.post("/api/dingtalk/test")
def test_dingtalk(payload: DingTalkTestRequest):
    ok, message = _send_dingtalk_text(payload.content)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message}


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
        relative_url = f"/reports/{report_dir.name}/index.html"
        reports.append(
            {
                "id": report_dir.name,
                "url": relative_url,
                "absolute_url": _absolute_report_url(relative_url),
                "ticker": meta.get("ticker") or report_dir.name,
                "depth": meta.get("depth"),
                "generated_at": meta.get("generated_at"),
                "one_liner": meta.get("one_liner"),
                "size_kb": meta.get("size_kb"),
            }
        )
    return reports
