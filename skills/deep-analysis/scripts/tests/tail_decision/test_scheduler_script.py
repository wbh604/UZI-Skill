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
    assert "TUSHARE_TOKEN" not in completed.stdout
