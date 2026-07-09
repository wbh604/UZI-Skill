"""FastAPI application for UZI Web server service."""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from src.config import get_settings
from src.services.dingtalk_notifier import DingTalkNotifier
from src.services.job_queue import JobQueue, parse_tickers
from src.services.uzi_runner import UziRunner

Depth = Literal["lite", "medium", "deep"]

settings = get_settings()
notifier = DingTalkNotifier(settings)
runner = UziRunner(settings)
queue = JobQueue(settings=settings, runner=runner, notifier=notifier)

templates = Jinja2Templates(directory=str(settings.root_dir / "web" / "templates"))
app = FastAPI(title="UZI Web", version="0.3.1")
app.mount("/reports", StaticFiles(directory=str(settings.reports_dir), html=True), name="reports")


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=64)
    depth: Depth = settings.default_depth  # type: ignore[assignment]
    no_resume: bool = False
    notify: bool = settings.dingtalk_notify_default


class BatchAnalyzeRequest(BaseModel):
    tickers: str = Field(..., min_length=1, max_length=4000)
    depth: Depth = settings.default_depth  # type: ignore[assignment]
    no_resume: bool = False
    notify: bool = settings.dingtalk_notify_default


class DingTalkTestRequest(BaseModel):
    content: str = "股票：这是一条来自 UZI Web 的钉钉测试消息。"


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "run_py": str(settings.run_py),
        "reports_dir": str(settings.reports_dir),
        "logs_dir": str(settings.logs_dir),
        "active_jobs": queue.active_jobs_count(),
        "max_parallel_jobs": settings.max_parallel_jobs,
        "dingtalk_configured": notifier.configured,
        "schedule_enabled": settings.schedule_enabled,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "default_depth": settings.default_depth,
            "default_notify": settings.dingtalk_notify_default,
        },
    )


@app.get("/api/config")
def get_config() -> dict:
    return {
        "default_depth": settings.default_depth,
        "max_parallel_jobs": settings.max_parallel_jobs,
        "max_queue_size": settings.max_queue_size,
        "reports_dir": str(settings.reports_dir),
        "logs_dir": str(settings.logs_dir),
        "dingtalk_configured": notifier.configured,
        "dingtalk_secret_configured": notifier.secret_configured,
        "default_notify": settings.dingtalk_notify_default,
        "public_base_url": settings.public_base_url,
        "schedule": {
            "enabled": settings.schedule_enabled,
            "times": settings.schedule_times,
            "tickers": settings.schedule_tickers,
            "depth": settings.schedule_depth,
            "notify": settings.schedule_notify,
        },
    }


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest):
    job = queue.submit(
        ticker=payload.ticker,
        depth=payload.depth,
        no_resume=payload.no_resume,
        notify=payload.notify,
        source="manual",
    )
    return JSONResponse(job.to_dict(settings.job_log_tail_chars))


@app.post("/api/analyze/batch")
def analyze_batch(payload: BatchAnalyzeRequest):
    tickers = parse_tickers(payload.tickers)
    if not tickers:
        raise HTTPException(status_code=400, detail="no valid tickers found")
    if len(tickers) > 50:
        raise HTTPException(status_code=400, detail="batch size is limited to 50 tickers")

    batch_id, jobs = queue.submit_batch(
        tickers=tickers,
        depth=payload.depth,
        no_resume=payload.no_resume,
        notify=payload.notify,
        source="batch",
    )

    if payload.notify and notifier.configured:
        notifier.send_text(
            f"股票 UZI 批量任务已提交\n"
            f"批次：{batch_id}\n"
            f"数量：{len(jobs)}\n"
            f"深度：{payload.depth}"
        )

    return {
        "batch_id": batch_id,
        "count": len(jobs),
        "jobs": [job.to_dict(settings.job_log_tail_chars) for job in jobs],
    }


@app.post("/api/dingtalk/test")
def test_dingtalk(payload: DingTalkTestRequest):
    ok, message = notifier.send_text(payload.content)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message}


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    return [job.to_dict(settings.job_log_tail_chars) for job in queue.list_jobs()]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict(settings.job_log_tail_chars)


@app.get("/api/reports")
def list_reports() -> list[dict]:
    return queue.list_reports()
