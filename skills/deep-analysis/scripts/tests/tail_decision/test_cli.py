import json
from pathlib import Path
import subprocess
import sys


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

import run_tail_decision as cli


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


def test_cli_uses_the_production_gateway_module_without_hardcoded_universe():
    assert cli.CredentialFreeGateway.__module__ == "lib.tail_decision.gateway"
    assert not hasattr(cli, "_CredentialFreeGateway")
    assert not hasattr(cli, "DEFAULT_ETFS")
    assert not hasattr(cli, "DEFAULT_STOCKS")


def test_cli_accepts_a_separate_forward_state_root(tmp_path):
    state_root = tmp_path / "state"

    args = cli._parser().parse_args(
        [
            "--phase",
            "warmup",
            "--state-root",
            str(state_root),
        ]
    )

    assert args.state_root == state_root


def test_final_cli_advances_the_append_only_paper_ledger(tmp_path):
    state_root = tmp_path / "state"
    command = [
        sys.executable,
        "skills/deep-analysis/scripts/run_tail_decision.py",
        "--phase",
        "final",
        "--as-of",
        "2026-08-04T14:30:00+08:00",
        "--offline-fixture",
        "--output-root",
        str(tmp_path / "output"),
        "--state-root",
        str(state_root),
    ]

    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ledger_events"] == 1
    assert (state_root / "ledger" / "events.jsonl").is_file()
