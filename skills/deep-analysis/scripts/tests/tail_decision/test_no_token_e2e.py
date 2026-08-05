import json
import os
from pathlib import Path
import subprocess
import sys


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision import DecisionConfig, DecisionRecorder, TailDecisionWorkflow


def test_no_token_end_to_end_records_bounded_portfolio(tmp_path):
    assert DecisionConfig().effective_position_cap_cny == 12_000.0
    assert DecisionRecorder(tmp_path).root == tmp_path
    assert TailDecisionWorkflow.__name__ == "TailDecisionWorkflow"

    env = os.environ.copy()
    env.pop("TUSHARE_TOKEN", None)
    completed = subprocess.run(
        [
            sys.executable,
            "skills/deep-analysis/scripts/run_tail_decision.py",
            "--phase",
            "final",
            "--as-of",
            "2026-08-03T14:30:00+08:00",
            "--offline-fixture",
            "--position-cap",
            "12000",
            "--available-cash",
            "12000",
            "--output-root",
            str(tmp_path),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert 0 < summary["total_exposure"] <= 12_000.0
    assert len(summary["allocations"]) <= 1
    artifacts = list(tmp_path.rglob("*.json"))
    assert artifacts
    assert all(
        "TUSHARE_TOKEN" not in path.read_text(encoding="utf-8")
        for path in artifacts
    )
