"""Analyzer-side scheduler service for UZI Web."""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime

from src.config import Settings
from src.services.dingtalk_notifier import DingTalkNotifier
from src.services.job_queue import JobQueue

logger = logging.getLogger(__name__)


class UziScheduler:
    def __init__(self, settings: Settings, queue: JobQueue, notifier: DingTalkNotifier) -> None:
        self.settings = settings
        self.queue = queue
        self.notifier = notifier
        self._last_schedule_key: str | None = None

    def _valid_schedule_times(self) -> list[str]:
        values: list[str] = []
        for item in self.settings.schedule_times:
            if len(item) == 5 and item[2] == ":" and item[:2].isdigit() and item[3:].isdigit():
                values.append(item)
        return values

    def submit_due_jobs(self) -> int:
        if not self.settings.schedule_enabled:
            return 0
        schedule_times = self._valid_schedule_times()
        tickers = self.settings.schedule_tickers
        if not schedule_times or not tickers:
            return 0

        now = datetime.now()
        current = now.strftime("%H:%M")
        if current not in schedule_times:
            return 0

        schedule_key = f"{now.strftime('%Y-%m-%d')} {current}"
        if self._last_schedule_key == schedule_key:
            return 0
        self._last_schedule_key = schedule_key

        batch_id = f"schedule_{now.strftime('%Y%m%d_%H%M')}_{uuid.uuid4().hex[:6]}"
        submitted = 0
        for ticker in tickers:
            try:
                self.queue.submit(
                    ticker=ticker,
                    depth=self.settings.schedule_depth,
                    no_resume=False,
                    notify=self.settings.schedule_notify,
                    source="schedule",
                    batch_id=batch_id,
                )
                submitted += 1
            except Exception as exc:
                logger.warning("Failed to submit scheduled ticker %s: %s", ticker, exc)

        if submitted and self.settings.schedule_notify:
            self.notifier.send_text(
                f"股票 UZI 定时任务已提交\n"
                f"批次：{batch_id}\n"
                f"数量：{submitted}\n"
                f"深度：{self.settings.schedule_depth}\n"
                f"时间：{schedule_key}"
            )
        logger.info("Scheduled UZI jobs submitted: %s", submitted)
        return submitted

    def run_forever(self) -> None:
        if not self.settings.schedule_enabled:
            logger.warning(
                "UZI analyzer started but UZI_SCHEDULE_ENABLED=false. "
                "Set UZI_SCHEDULE_ENABLED=true and UZI_SCHEDULE_TIMES to enable scheduled jobs."
            )
        while True:
            self.submit_due_jobs()
            time.sleep(20)
