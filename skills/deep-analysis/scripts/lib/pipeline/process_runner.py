"""Small process scheduler used to enforce hard fetcher timeouts."""
from __future__ import annotations

import multiprocessing as mp
import time
from dataclasses import dataclass, field
from multiprocessing.connection import wait
from typing import Any, Callable


@dataclass(frozen=True)
class ProcessJob:
    key: str
    target: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    timeout_sec: float = 120.0
    serial_group: str | None = None


@dataclass(frozen=True)
class ProcessOutcome:
    key: str
    value: Any = None
    error: str | None = None
    timed_out: bool = False


def _process_entry(conn, target, args, kwargs) -> None:
    try:
        conn.send((True, target(*args, **kwargs), None))
    except BaseException as exc:
        try:
            conn.send((False, None, f"{type(exc).__name__}: {str(exc)[:300]}"))
        except BaseException:
            pass
    finally:
        conn.close()


def _terminate(process) -> None:
    if process.is_alive():
        process.terminate()
        process.join(timeout=1.0)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=1.0)


def run_process_jobs(
    jobs: list[ProcessJob],
    *,
    max_workers: int,
    overall_timeout: float,
    on_outcome: Callable[[ProcessOutcome], None] | None = None,
) -> list[ProcessOutcome]:
    """Run picklable callables in child processes that can be terminated."""
    if max_workers < 1:
        raise ValueError("max_workers must be >= 1")
    if overall_timeout <= 0:
        raise ValueError("overall_timeout must be > 0")
    keys = [job.key for job in jobs]
    if len(keys) != len(set(keys)):
        raise ValueError("process job keys must be unique")

    ctx = mp.get_context("spawn")
    pending = list(jobs)
    active: dict[str, tuple[ProcessJob, Any, Any, float]] = {}
    outcomes: list[ProcessOutcome] = []
    started = time.monotonic()

    def record(outcome: ProcessOutcome) -> None:
        outcomes.append(outcome)
        if on_outcome is not None:
            on_outcome(outcome)

    def launch_available() -> None:
        active_groups = {
            job.serial_group
            for job, _process, _conn, _started in active.values()
            if job.serial_group
        }
        while pending and len(active) < max_workers:
            selected = next(
                (
                    index
                    for index, job in enumerate(pending)
                    if not job.serial_group or job.serial_group not in active_groups
                ),
                None,
            )
            if selected is None:
                return
            job = pending.pop(selected)
            parent_conn, child_conn = ctx.Pipe(duplex=False)
            process = ctx.Process(
                target=_process_entry,
                args=(child_conn, job.target, job.args, job.kwargs),
                name=f"uzi-fetch-{job.key}",
            )
            process.start()
            child_conn.close()
            active[job.key] = (job, process, parent_conn, time.monotonic())
            if job.serial_group:
                active_groups.add(job.serial_group)

    try:
        while pending or active:
            launch_available()
            now = time.monotonic()
            overall_remaining = overall_timeout - (now - started)
            if overall_remaining <= 0:
                for key, (_job, process, conn, _job_started) in list(active.items()):
                    _terminate(process)
                    conn.close()
                    record(ProcessOutcome(key=key, error="overall timeout", timed_out=True))
                for job in pending:
                    record(ProcessOutcome(key=job.key, error="overall timeout before start", timed_out=True))
                active.clear()
                pending.clear()
                break

            nearest_job_timeout = min(
                job.timeout_sec - (now - job_started)
                for job, _process, _conn, job_started in active.values()
            )
            poll_timeout = max(0.0, min(0.05, overall_remaining, nearest_job_timeout))
            ready = wait([item[2] for item in active.values()], timeout=poll_timeout) if active else []

            for conn in ready:
                key = next(key for key, item in active.items() if item[2] is conn)
                job, process, _conn, _job_started = active.pop(key)
                try:
                    ok, value, error = conn.recv()
                except (EOFError, OSError) as exc:
                    ok, value, error = False, None, f"worker pipe failed: {type(exc).__name__}: {exc}"
                finally:
                    conn.close()
                    process.join(timeout=1.0)
                    if process.is_alive():
                        _terminate(process)
                record(ProcessOutcome(key=job.key, value=value if ok else None, error=error))

            now = time.monotonic()
            for key, (job, process, conn, job_started) in list(active.items()):
                if now - job_started >= job.timeout_sec:
                    _terminate(process)
                    conn.close()
                    active.pop(key)
                    record(
                        ProcessOutcome(
                            key=key,
                            error=f"fetcher timeout > {job.timeout_sec:g}s",
                            timed_out=True,
                        )
                    )
    finally:
        for _key, (_job, process, conn, _job_started) in active.items():
            _terminate(process)
            conn.close()

    return outcomes
