"""Deterministic, read-only access to validated local archive partitions."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re

import pandas as pd


class ArchiveDataError(RuntimeError):
    """Raised when required archive data is absent or malformed."""


class ArchiveReader:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def latest_partition(
        self, dataset: str, as_of: date | datetime
    ) -> Path | None:
        dataset_root = self._dataset_root(dataset)
        if not dataset_root.is_dir():
            return None
        cutoff = as_of.date() if isinstance(as_of, datetime) else as_of
        eligible: list[tuple[date, str, Path]] = []
        for path in dataset_root.iterdir():
            if not path.is_file() or not _is_supported(path):
                continue
            partition_date = _partition_date(path)
            if partition_date is not None and partition_date <= cutoff:
                eligible.append((partition_date, path.name, path))
        if not eligible:
            return None
        return max(eligible)[2]

    def read_latest(
        self,
        dataset: str,
        as_of: date | datetime,
        *,
        required: bool = True,
    ) -> pd.DataFrame:
        partition = self.latest_partition(dataset, as_of)
        if partition is None:
            if required:
                raise ArchiveDataError(
                    f"no partition for dataset {dataset!r} at or before {as_of}"
                )
            return pd.DataFrame()
        try:
            if partition.name.lower().endswith(".parquet"):
                return pd.read_parquet(partition)
            return pd.read_csv(partition)
        except Exception as exc:
            raise ArchiveDataError(f"failed to read archive partition: {partition}") from exc

    def read_trade_dates(
        self, start: date | datetime, end: date | datetime
    ) -> list[str]:
        start_date = start.date() if isinstance(start, datetime) else start
        end_date = end.date() if isinstance(end, datetime) else end
        if end_date < start_date:
            raise ValueError("end must not be before start")
        frame = self.read_latest("trade_cal", end_date)
        date_column = next(
            (name for name in ("cal_date", "trade_date") if name in frame.columns),
            None,
        )
        if date_column is None:
            raise ArchiveDataError("trade_cal partition has no calendar date column")
        parsed_dates = pd.to_datetime(
            frame[date_column].astype(str), format="%Y%m%d", errors="coerce"
        )
        if parsed_dates.isna().any():
            raise ArchiveDataError("trade_cal partition contains malformed dates")
        open_mask = pd.Series(True, index=frame.index)
        if "is_open" in frame.columns:
            open_mask = (
                frame["is_open"]
                .astype(str)
                .str.strip()
                .isin({"1", "1.0", "true", "True", "Y"})
            )
        range_mask = (parsed_dates.dt.date >= start_date) & (
            parsed_dates.dt.date <= end_date
        )
        return sorted(
            set(parsed_dates[open_mask & range_mask].dt.strftime("%Y%m%d").tolist())
        )

    def _dataset_root(self, dataset: str) -> Path:
        dataset_path = Path(dataset)
        if (
            not dataset
            or dataset_path.is_absolute()
            or len(dataset_path.parts) != 1
            or dataset in {".", ".."}
        ):
            raise ValueError(f"invalid dataset name: {dataset!r}")
        return self.root / "normalized" / dataset


def _is_supported(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".csv", ".csv.gz", ".parquet"))


def _partition_date(path: Path) -> date | None:
    match = re.search(r"(?<!\d)(\d{8})(?!\d)", path.name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError as exc:
        raise ArchiveDataError(f"invalid partition date in filename: {path.name}") from exc
