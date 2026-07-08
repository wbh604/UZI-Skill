#!/usr/bin/env python3
"""DSA-style entrypoint for UZI Web.

Usage:
    python main.py                                # analyzer / scheduler service
    python main.py --serve-only --host 0.0.0.0   # Web/API service
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import uvicorn

from src.config import get_settings


def setup_logging(debug: bool = False) -> None:
    settings = get_settings()
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(level)
    root.addHandler(console)

    file_handler = logging.FileHandler(settings.logs_dir / "uzi_web.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root.addHandler(file_handler)


def run_server(host: str, port: int, debug: bool = False) -> None:
    setup_logging(debug=debug)
    logging.getLogger(__name__).info("Starting UZI Web server on %s:%s", host, port)
    uvicorn.run("src.api.app:app", host=host, port=port, reload=False)


def run_analyzer(debug: bool = False) -> None:
    setup_logging(debug=debug)
    logger = logging.getLogger(__name__)
    settings = get_settings()

    from src.services.dingtalk_notifier import DingTalkNotifier
    from src.services.job_queue import JobQueue
    from src.services.scheduler import UziScheduler
    from src.services.uzi_runner import UziRunner

    notifier = DingTalkNotifier(settings)
    runner = UziRunner(settings)
    queue = JobQueue(settings=settings, runner=runner, notifier=notifier)
    scheduler = UziScheduler(settings=settings, queue=queue, notifier=notifier)

    logger.info(
        "Starting UZI analyzer service; schedule_enabled=%s, schedule_times=%s, schedule_tickers=%s",
        settings.schedule_enabled,
        settings.schedule_times,
        settings.schedule_tickers,
    )
    scheduler.run_forever()


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="UZI Web / Docker entrypoint")
    parser.add_argument("--serve-only", action="store_true", help="Only start the Web/API service")
    parser.add_argument("--host", default=settings.web_host, help="Web/API bind host")
    parser.add_argument("--port", type=int, default=settings.web_port, help="Web/API bind port")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.serve_only:
        run_server(args.host, args.port, debug=args.debug)
    else:
        run_analyzer(debug=args.debug)


if __name__ == "__main__":
    main()
