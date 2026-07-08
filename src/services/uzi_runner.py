"""Subprocess runner that reuses the existing UZI run.py entrypoint."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from src.config import Settings
from src.services.models import Job

LogCallback = Callable[[str], None]


class UziRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_command(self, ticker: str, depth: str, out_dir: Path, no_resume: bool = False) -> list[str]:
        cmd = [
            sys.executable,
            str(self.settings.run_py),
            ticker,
            "--depth",
            depth,
            "--no-browser",
            "--output-dir",
            str(out_dir),
        ]
        if no_resume:
            cmd.append("--no-resume")
        return cmd

    @staticmethod
    def read_report_meta(out_dir: Path) -> dict | None:
        meta_path = out_dir / "report.meta.json"
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def run(self, job: Job, out_dir: Path, on_log: LogCallback | None = None) -> tuple[int, str]:
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("UZI_CLI_ONLY", "1")

        proc = subprocess.Popen(
            job.command,
            cwd=str(self.settings.root_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert proc.stdout is not None

        chunks: list[str] = []
        for line in proc.stdout:
            chunks.append(line)
            if on_log:
                on_log(line)
        return proc.wait(), "".join(chunks)
