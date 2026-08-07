"""DingTalk robot notification support for UZI Web."""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from datetime import datetime
from urllib.parse import quote_plus

import requests

from src.config import Settings
from src.services.models import Job

logger = logging.getLogger(__name__)


class DingTalkNotifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.dingtalk_webhook_url)

    @property
    def secret_configured(self) -> bool:
        return bool(self.settings.dingtalk_secret)

    def _signed_url(self) -> str:
        webhook = self.settings.dingtalk_webhook_url
        secret = self.settings.dingtalk_secret
        if not secret:
            return webhook

        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        digest = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = quote_plus(base64.b64encode(digest).decode("utf-8"))
        separator = "&" if "?" in webhook else "?"
        return f"{webhook}{separator}timestamp={timestamp}&sign={sign}"

    def send_text(self, content: str) -> tuple[bool, str]:
        if not self.configured:
            return False, "DINGTALK_WEBHOOK_URL is not configured"

        # Keep the keyword at the beginning for DingTalk robots using keyword security.
        if "股票" not in content:
            content = f"股票：{content}"

        try:
            resp = requests.post(
                self._signed_url(),
                json={"msgtype": "text", "text": {"content": content}},
                timeout=12,
            )
        except Exception as exc:
            logger.warning("DingTalk request failed: %s", exc)
            return False, f"request failed: {exc}"

        try:
            data = resp.json()
        except Exception:
            data = {"errmsg": resp.text[:300]}

        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}: {data}"

        errcode = data.get("errcode")
        if errcode not in (0, None):
            return False, f"DingTalk errcode={errcode}, errmsg={data.get('errmsg')}"
        return True, data.get("errmsg") or "ok"

    def absolute_report_url(self, relative_url: str | None) -> str | None:
        if not relative_url:
            return None
        if self.settings.public_base_url:
            return f"{self.settings.public_base_url}{relative_url}"
        return relative_url

    def format_job_message(self, job: Job) -> str:
        ok = job.status == "success"
        status_text = "成功" if ok else "失败"
        lines = [
            f"股票 UZI 报告任务{status_text}",
            f"标的：{job.ticker}",
            f"深度：{job.depth}",
            f"来源：{job.source}",
        ]
        report_url = self.absolute_report_url(job.report_url)
        if report_url:
            lines.append(f"报告：{report_url}")
        if job.meta and job.meta.get("one_liner"):
            lines.append(f"摘要：{job.meta.get('one_liner')}")
        if job.error:
            lines.append(f"错误：{job.error}")
        lines.append(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return "\n".join(lines)

    def notify_job_finished(self, job: Job) -> tuple[bool, str]:
        if not job.notify:
            return True, "skip"
        return self.send_text(self.format_job_message(job))
