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


def test_recorder_is_append_only_and_redacts_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("TUSHARE_TOKEN", "secret-value")
    recorder = DecisionRecorder(tmp_path)

    first = recorder.record(
        decision_run(run_id="run-a"),
        raw_quotes={"token": "secret-value"},
    )
    second = recorder.record(decision_run(run_id="run-b"), raw_quotes={})

    assert first != second
    assert first.exists() and second.exists()
    assert first.with_suffix(".md").exists()
    assert "secret-value" not in first.read_text(encoding="utf-8")
    assert "secret-value" not in first.with_suffix(".md").read_text(encoding="utf-8")
    assert json.loads(first.read_text(encoding="utf-8"))["status"] == "recommended"


def test_recorder_refuses_same_run_id_at_a_different_timestamp(tmp_path):
    recorder = DecisionRecorder(tmp_path)
    first_run = decision_run(run_id="run-a")
    recorder.record(first_run, raw_quotes={})

    with pytest.raises(FileExistsError, match="run_id already recorded"):
        recorder.record(
            replace(first_run, as_of=first_run.as_of + timedelta(seconds=1)),
            raw_quotes={},
        )
