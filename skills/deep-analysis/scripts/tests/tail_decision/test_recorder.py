import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.recorder import DecisionRecorder
from .fixtures import decision_run


def recommended_run_with_one_allocation():
    run = decision_run(run_id="one-allocation")
    return replace(run, allocations=run.allocations[:1])


def test_recorder_is_append_only_and_redacts_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-value")
    recorder = DecisionRecorder(tmp_path)

    first = recorder.record(
        replace(decision_run(run_id="run-a"), allocations=()),
        raw_quotes={"token": "secret-value"},
    )
    second = recorder.record(
        replace(decision_run(run_id="run-b"), allocations=()), raw_quotes={}
    )

    assert first != second
    assert first.exists() and second.exists()
    assert first.with_suffix(".md").exists()
    assert "secret-value" not in first.read_text(encoding="utf-8")
    assert "secret-value" not in first.with_suffix(".md").read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["status"] == "recommended"


def test_recorder_refuses_same_run_id_at_a_different_timestamp(tmp_path):
    recorder = DecisionRecorder(tmp_path)
    first_run = replace(decision_run(run_id="run-a"), allocations=())
    recorder.record(first_run, raw_quotes={})

    with pytest.raises(FileExistsError, match="run_id already recorded"):
        recorder.record(
            replace(first_run, as_of=first_run.as_of + timedelta(seconds=1)),
            raw_quotes={},
        )


def test_recorder_audits_funnel_without_rendering_finalists_as_orders(tmp_path):
    recorder = DecisionRecorder(tmp_path)
    path = recorder.record(
        recommended_run_with_one_allocation(),
        {
            "funnel_audit": {
                "research_stocks": 300,
                "observation_stocks": 30,
                "research_etfs": 10,
                "observation_etfs": 10,
                "reasons": ("research_stock_target_met",),
            },
            "research_evidence": {
                "300170.SZ": {
                    "source_dates": ("2026-08-05",),
                    "reasons": ("uzi_stale",),
                },
            },
            "cash_audit": {
                "configured_position_cap_cny": 12_000.0,
                "available_cash_cny": 12_000.0,
                "effective_position_cap_cny": 12_000.0,
            },
        },
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["audit"]["funnel"]["research_stocks"] == 300
    assert payload["audit"]["evidence"]["reason_codes"] == ["uzi_stale"]
    assert payload["audit"]["cash"]["effective_position_cap_cny"] == 12_000.0
    assert len(payload["allocations"]) == 1

    markdown = path.with_suffix(".md").read_text(encoding="utf-8")
    assert "## Audit Summary" in markdown
    assert "## ETF Candidates" not in markdown
    assert "## Stock Candidates" not in markdown
    assert markdown.count("Buy plan") == 1


def test_recorder_refuses_multiple_allocations(tmp_path):
    with pytest.raises(ValueError, match="at most one allocation"):
        DecisionRecorder(tmp_path).record(decision_run(run_id="multiple"), {})
