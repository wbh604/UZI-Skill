import json
from pathlib import Path
import subprocess
import sys


def test_cli_runs_without_tushare_token(tmp_path, monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    command = [
        sys.executable,
        "skills/deep-analysis/scripts/run_tail_decision.py",
        "--phase",
        "preview",
        "--as-of",
        "2026-08-03T14:10:00+08:00",
        "--offline-fixture",
        "--output-root",
        str(tmp_path),
    ]

    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] in {"recommended", "watch_only", "no_trade"}
    assert payload["total_exposure"] <= 8_000.0
    assert list(Path(tmp_path).rglob("*.json"))
