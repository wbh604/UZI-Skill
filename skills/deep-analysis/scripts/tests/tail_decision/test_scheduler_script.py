from pathlib import Path
import subprocess


def test_scheduler_whatif_lists_all_local_cli_phases_without_credentials():
    script = Path("scripts/install_tail_decision_tasks.ps1")
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-WhatIf",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    lines = [line for line in completed.stdout.splitlines() if line.startswith("WHATIF ")]
    assert len(lines) == 7
    assert any("14:10" in line and "--phase preview" in line for line in lines)
    assert any("14:30" in line and "--phase final" in line for line in lines)
    assert any("09:25" in line and "--phase exit_open" in line for line in lines)
    assert "run_tail_decision.py" in completed.stdout
    assert "--state-root" in completed.stdout
    assert "TUSHARE_TOKEN" not in completed.stdout


def test_scheduler_health_whatif_lists_the_same_seven_tasks():
    script = Path("scripts/check_tail_decision_tasks.ps1")
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-WhatIf",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    lines = [
        line for line in completed.stdout.splitlines() if line.startswith("CHECKSPEC ")
    ]
    assert len(lines) == 7
    assert any("UZI-Tail-Final" in line and "14:30" in line for line in lines)
    assert any("UZI-Tail-ExitCheck" in line and "09:35" in line for line in lines)


def test_scheduler_health_allows_windows_task_has_not_run_status():
    script = Path("scripts/check_tail_decision_tasks.ps1").read_text(encoding="utf-8")

    assert "267011" in script
