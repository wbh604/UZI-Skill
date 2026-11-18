from __future__ import annotations

from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]


def test_legacy_collect_uses_killable_process_runner():
    src = (SCRIPTS / "run_real_test.py").read_text(encoding="utf-8")
    assert "run_process_jobs" in src
    assert "ThreadPoolExecutor" not in src, "legacy collector must not use non-killable threads"


def test_fetch_job_dispatches_top_level_fetcher(monkeypatch):
    import run_real_test as rrt

    monkeypatch.setattr(rrt, "FETCHER_MAP", [("fake_fetcher", "99_fake", lambda ticker, raw: (ticker,))])
    monkeypatch.setattr(rrt, "run_fetcher", lambda name, args: {"data": {"name": name, "args": args}})

    assert rrt._fetch_job("fake_fetcher", "600000.SH", {}) == {
        "data": {"name": "fake_fetcher", "args": ("600000.SH",)}
    }
