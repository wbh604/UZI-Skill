import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

import run_tail_decision as cli


def run_offline_cli(tmp_path, *extra_args):
    command = [
        sys.executable,
        "skills/deep-analysis/scripts/run_tail_decision.py",
        "--phase",
        "final",
        "--as-of",
        "2026-08-05T14:30:00+08:00",
        "--offline-fixture",
        "--output-root",
        str(tmp_path),
        *extra_args,
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


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
    assert payload["total_exposure"] <= 12_000.0
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


def test_cli_defaults_to_user_approved_12000_cash_cap():
    args = cli._parser().parse_args(["--phase", "preview"])

    assert args.position_cap == 12_000.0
    assert args.available_cash == 12_000.0


def test_cli_payload_exposes_configured_available_and_effective_caps(tmp_path):
    payload = run_offline_cli(
        tmp_path,
        "--position-cap",
        "12000",
        "--available-cash",
        "7600",
    )

    assert payload["configured_position_cap_cny"] == 12_000.0
    assert payload["available_cash_cny"] == 7_600.0
    assert payload["effective_position_cap_cny"] == 7_600.0
    assert payload["total_exposure"] <= 7_600.0
    assert len(payload["allocations"]) <= 1


def test_legacy_max_exposure_alias_cannot_override_explicit_position_cap(capsys):
    exit_code = cli.main(
        [
            "--phase",
            "preview",
            "--position-cap",
            "12000",
            "--max-exposure",
            "4000",
            "--offline-fixture",
        ]
    )

    assert exit_code == 3
    assert json.loads(capsys.readouterr().out)["reasons"] == ["invalid_configuration"]


def test_legacy_max_exposure_alias_maps_to_configured_position_cap(tmp_path):
    payload = run_offline_cli(tmp_path, "--max-exposure", "7600")

    assert payload["configured_position_cap_cny"] == 7_600.0
    assert payload["effective_position_cap_cny"] == 7_600.0


def test_cli_rejects_nonpositive_available_cash(capsys):
    exit_code = cli.main(
        ["--phase", "preview", "--available-cash", "0", "--offline-fixture"]
    )

    assert exit_code == 3
    assert json.loads(capsys.readouterr().out)["reasons"] == ["invalid_configuration"]


@pytest.mark.parametrize(
    ("flag", "value"),
    (
        ("--position-cap", "nan"),
        ("--available-cash", "inf"),
        ("--account-assets", "-inf"),
    ),
)
def test_cli_rejects_nonfinite_cash_configuration_without_nonstandard_json(
    tmp_path, flag, value
):
    completed = subprocess.run(
        [
            sys.executable,
            "skills/deep-analysis/scripts/run_tail_decision.py",
            "--phase",
            "preview",
            "--offline-fixture",
            "--output-root",
            str(tmp_path),
            f"{flag}={value}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 3
    assert json.loads(completed.stdout) == {
        "status": "blocked",
        "reasons": ["invalid_configuration"],
    }
    assert "NaN" not in completed.stdout
    assert "Infinity" not in completed.stdout


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
    assert payload["forward_release_state"] == "collecting"
    assert (state_root / "ledger" / "events.jsonl").is_file()
    assert (
        tmp_path / "output" / "reports" / "tail_decision" / "forward" / "latest.json"
    ).is_file()
