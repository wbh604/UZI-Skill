"""Append-only normalized forward quote snapshots and intraday reconstruction."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path
import time
from typing import Iterator, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from .contracts import QuoteSnapshot


SHANGHAI = ZoneInfo("Asia/Shanghai")
_SOURCE_PRIORITY = {"eastmoney": 0, "tencent": 1}
_BAR_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "source",
    "fetched_at",
)


class SnapshotStoreError(RuntimeError):
    """Raised when snapshot evidence cannot be safely written or reconstructed."""


class QuoteSnapshotStore:
    def __init__(self, root: str | Path, *, lock_timeout_seconds: float = 1.0):
        if lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be positive")
        self.root = Path(root)
        self.snapshot_root = self.root / "cache" / "tail_decision" / "snapshots"
        self.lock_timeout_seconds = lock_timeout_seconds

    def append(
        self,
        *,
        phase: str,
        quotes: Mapping[str, Sequence[QuoteSnapshot]],
    ) -> Path:
        if not phase.strip():
            raise ValueError("phase must not be empty")
        records: list[dict[str, object]] = []
        days: set[str] = set()
        for instrument_id in sorted(quotes):
            for snapshot in sorted(
                quotes[instrument_id],
                key=lambda item: (
                    item.timestamp,
                    _SOURCE_PRIORITY.get(item.source, 99),
                    item.fetched_at,
                ),
            ):
                if snapshot.instrument_id != instrument_id:
                    raise ValueError("quote mapping key does not match instrument_id")
                local_day = snapshot.timestamp.astimezone(SHANGHAI).strftime("%Y%m%d")
                days.add(local_day)
                record = {
                    "phase": phase,
                    **{
                        key: value.value if isinstance(value, Enum) else value
                        for key, value in asdict(snapshot).items()
                    },
                }
                record["timestamp"] = snapshot.timestamp.isoformat()
                record["fetched_at"] = snapshot.fetched_at.isoformat()
                records.append(record)
        if not records:
            raise ValueError("quotes must contain at least one snapshot")
        if len(days) != 1:
            raise ValueError("one append call must contain a single Shanghai date")

        self.snapshot_root.mkdir(parents=True, exist_ok=True)
        path = self.snapshot_root / f"{next(iter(days))}.jsonl"
        lock_path = path.with_suffix(".jsonl.lock")
        lines = "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for record in records
        )
        with _exclusive_lock(lock_path, self.lock_timeout_seconds):
            with path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(lines)
                stream.flush()
                os.fsync(stream.fileno())
        return path

    def read_intraday(
        self,
        instrument_id: str,
        as_of: datetime,
    ) -> pd.DataFrame:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        local_as_of = as_of.astimezone(SHANGHAI)
        path = self.snapshot_root / f"{local_as_of.strftime('%Y%m%d')}.jsonl"
        if not path.is_file():
            return _empty_bars()

        records: list[dict[str, object]] = []
        try:
            with path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    if line.strip():
                        records.append(json.loads(line))
        except (OSError, json.JSONDecodeError) as exc:
            raise SnapshotStoreError(f"failed to read snapshot file: {path}") from exc
        if not records:
            return _empty_bars()

        frame = pd.DataFrame(records)
        required = {
            "instrument_id",
            "timestamp",
            "fetched_at",
            "source",
            "last_price",
            "open",
            "high",
            "low",
            "volume",
            "amount",
        }
        if not required.issubset(frame.columns):
            raise SnapshotStoreError(f"snapshot file has incomplete records: {path}")
        frame = frame[frame["instrument_id"].astype(str) == instrument_id].copy()
        if frame.empty:
            return _empty_bars()

        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        frame["fetched_at"] = pd.to_datetime(frame["fetched_at"], utc=True, errors="coerce")
        frame = frame.dropna(subset=["timestamp", "fetched_at"])
        cutoff = pd.Timestamp(local_as_of).tz_convert("UTC")
        frame = frame[frame["timestamp"] <= cutoff]
        if frame.empty:
            return _empty_bars()

        frame["source_rank"] = frame["source"].map(_SOURCE_PRIORITY).fillna(99)
        frame = frame.sort_values(
            ["timestamp", "source_rank", "fetched_at"],
            kind="stable",
        )
        frame = frame.drop_duplicates(
            ["instrument_id", "source", "timestamp", "fetched_at"],
            keep="first",
        )
        frame = frame.drop_duplicates("timestamp", keep="first")
        for column in ("open", "high", "low", "last_price", "volume", "amount"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(
            subset=["open", "high", "low", "last_price", "volume", "amount"]
        )
        if frame.empty:
            return _empty_bars()

        frame["volume"] = _counter_deltas(frame["volume"])
        frame["amount"] = _counter_deltas(frame["amount"])
        frame["close"] = frame["last_price"]
        frame["timestamp"] = frame["timestamp"].dt.tz_convert(SHANGHAI)
        frame["fetched_at"] = frame["fetched_at"].dt.tz_convert(SHANGHAI)
        return frame.loc[:, _BAR_COLUMNS].reset_index(drop=True)


def _counter_deltas(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0).clip(lower=0.0)
    delta = numeric.diff()
    delta.iloc[0] = numeric.iloc[0]
    return delta.where(delta >= 0.0, numeric)


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame(columns=_BAR_COLUMNS)


@contextmanager
def _exclusive_lock(path: Path, timeout_seconds: float) -> Iterator[None]:
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise SnapshotStoreError(f"snapshot lock timeout: {path}") from exc
            time.sleep(0.01)
    os.close(descriptor)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)
