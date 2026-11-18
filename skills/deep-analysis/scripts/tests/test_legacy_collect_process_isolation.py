from __future__ import annotations

from pathlib import Path
import copy
from types import SimpleNamespace
import pytest


SCRIPTS = Path(__file__).resolve().parents[1]


def test_legacy_collect_persists_before_wave_finishes(monkeypatch):
    import run_real_test as rrt
    from lib import analysis_profile, cache
    from lib.pipeline import process_runner
    saved = []
    monkeypatch.setattr(cache, "write_task_output", lambda ticker, name, value: saved.append(copy.deepcopy(value)))
    monkeypatch.setattr(analysis_profile, "get_profile", lambda: SimpleNamespace(
        depth="medium", fetchers_enabled={"1_financials", "2_kline", "14_moat"}))
    monkeypatch.setattr(rrt, "run_fetcher", lambda *args: {"data": {"ticker": "600519.SH"}, "market": "A"})

    def run_jobs(jobs, *, max_workers, overall_timeout, on_outcome=None):
        if overall_timeout == 300:
            assert on_outcome is not None
            for job in jobs:
                result = process_runner.ProcessOutcome(
                    key=job.key, value={"data": {"synthetic": True}},
                    timed_out=job.key == "2_kline", error="test timeout" if job.key == "2_kline" else None)
                on_outcome(result)
            assert saved, "Completed dimensions must persist before the scheduler returns"
            assert saved[-1]["dimensions"]["2_kline"]["_timeout"] is True
            return []
        return [process_runner.ProcessOutcome(key=job.key, error="test crash") for job in jobs]

    monkeypatch.setattr(process_runner, "run_process_jobs", run_jobs)
    result = rrt.collect_raw_data("600519.SH", resume=False)
    assert result["dimensions"]["1_financials"]["data"] == {"synthetic": True}
    assert result["fund_managers"] == []
    assert result["similar_stocks"] == []


def test_legacy_collect_uses_killable_process_runner():
    src = (SCRIPTS / "run_real_test.py").read_text(encoding="utf-8")
    assert "run_process_jobs" in src
    assert "ThreadPoolExecutor" not in src, "legacy collector must not use non-killable threads"


@pytest.mark.parametrize("cached_materials", [False, True])
def test_legacy_futures_receives_materials_snapshot(monkeypatch, cached_materials):
    import run_real_test as rrt
    from lib import analysis_profile, cache
    from lib.pipeline import process_runner

    materials = {"data": {"materials_detail": [{"name": "synthetic material"}]}}
    monkeypatch.setattr(cache, "write_task_output", lambda *args: None)
    monkeypatch.setattr(cache, "read_task_output", lambda *args: {"dimensions": {"8_materials": materials}})
    monkeypatch.setattr(analysis_profile, "get_profile", lambda: SimpleNamespace(
        depth="medium", fetchers_enabled={"8_materials", "9_futures"}))
    monkeypatch.setattr(rrt, "run_fetcher", lambda *args: {"data": {"ticker": "600519.SH"}, "market": "A"})

    def run_jobs(jobs, *, max_workers, overall_timeout, on_outcome=None):
        keys = [job.key for job in jobs]
        if on_outcome is None:
            return [process_runner.ProcessOutcome(key=key, value={}) for key in keys]
        if "8_materials" in keys:
            assert not cached_materials
            assert keys == ["8_materials"]
            on_outcome(process_runner.ProcessOutcome(key="8_materials", value=materials))
        if "9_futures" in keys:
            assert 0 < overall_timeout <= 300
            assert jobs[0].args[2]["8_materials"] == materials
            on_outcome(process_runner.ProcessOutcome(key="9_futures", value={"data": {"checked": True}}))
        return []

    monkeypatch.setattr(process_runner, "run_process_jobs", run_jobs)
    result = rrt.collect_raw_data("600519.SH", resume=cached_materials)
    assert result["dimensions"]["9_futures"]["data"]["checked"] is True


def test_fetch_job_dispatches_top_level_fetcher(monkeypatch):
    import run_real_test as rrt

    monkeypatch.setattr(rrt, "FETCHER_MAP", [("fake_fetcher", "99_fake", lambda ticker, raw: (ticker,))])
    monkeypatch.setattr(rrt, "run_fetcher", lambda name, args: {"data": {"name": name, "args": args}})

    assert rrt._fetch_job("fake_fetcher", "600000.SH", {}) == {
        "data": {"name": "fake_fetcher", "args": ("600000.SH",)}
    }
