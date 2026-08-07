"""Optional Cloudflare Tunnel support for UZI Web.

This starts one tunnel for the Web server itself, so DingTalk can receive public
links like https://xxx.trycloudflare.com/reports/jobs/.../index.html.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
import time

from src.config import Settings

logger = logging.getLogger(__name__)


class PublicTunnelManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.public_url: str | None = None
        self.error: str | None = None
        self.proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return bool(self.proc and self.proc.poll() is None and self.public_url)

    def status(self) -> dict:
        return {
            "enabled": self.settings.public_tunnel_enabled,
            "running": self.running,
            "public_url": self.public_url,
            "error": self.error,
            "cloudflared_available": shutil.which("cloudflared") is not None,
        }

    def start_async(self) -> None:
        thread = threading.Thread(target=self.start, daemon=True)
        thread.start()

    def start(self) -> tuple[bool, str | None]:
        with self._lock:
            if self.running:
                return True, self.public_url
            self.error = None

            if not shutil.which("cloudflared"):
                self.error = "cloudflared not found in container"
                logger.warning(self.error)
                return False, None

            target = f"http://127.0.0.1:{self.settings.web_port}"
            logger.info("Starting Cloudflare tunnel for %s", target)
            self.proc = subprocess.Popen(
                ["cloudflared", "tunnel", "--url", target, "--no-autoupdate"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

        public_url = self._wait_for_public_url(timeout=self.settings.public_tunnel_timeout)
        with self._lock:
            if public_url:
                self.public_url = public_url.rstrip("/")
                os.environ["UZI_WEB_PUBLIC_BASE_URL"] = self.public_url
                logger.info("Cloudflare tunnel ready: %s", self.public_url)
                return True, self.public_url
            self.error = self.error or "Cloudflare tunnel did not return a public URL"
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
            logger.warning(self.error)
            return False, None

    def _wait_for_public_url(self, timeout: int) -> str | None:
        if not self.proc or not self.proc.stderr:
            return None

        pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stderr.readline()
            if not line:
                if self.proc.poll() is not None:
                    self.error = f"cloudflared exited with code {self.proc.returncode}"
                    return None
                time.sleep(0.1)
                continue
            logger.info("cloudflared: %s", line.strip())
            match = pattern.search(line)
            if match:
                return match.group(0)
        return None

    def stop(self) -> None:
        with self._lock:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
            self.proc = None
            self.public_url = None
