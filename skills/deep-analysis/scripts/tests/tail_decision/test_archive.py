from datetime import date
import gzip
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.archive import ArchiveDataError, ArchiveReader


def test_reader_chooses_latest_partition_not_after_as_of(tmp_path):
    root = tmp_path / "normalized" / "daily"
    root.mkdir(parents=True)
    for name in ("20260730.csv.gz", "20260731.csv.gz", "20260803.csv.gz"):
        with gzip.open(root / name, "wt", encoding="utf-8") as handle:
            handle.write(
                "ts_code,trade_date,close\n600406.SH," + name[:8] + ",25\n"
            )
    reader = ArchiveReader(tmp_path)
    selected = reader.latest_partition("daily", date(2026, 7, 31))
    assert selected.name == "20260731.csv.gz"


def test_read_latest_returns_empty_only_when_explicitly_optional(tmp_path):
    reader = ArchiveReader(tmp_path)
    with pytest.raises(ArchiveDataError, match="no partition"):
        reader.read_latest("daily", date(2026, 7, 31))
    assert reader.read_latest("daily", date(2026, 7, 31), required=False).empty


def test_read_latest_wraps_malformed_partition(tmp_path):
    root = tmp_path / "normalized" / "daily"
    root.mkdir(parents=True)
    (root / "20260731.csv.gz").write_bytes(b"not-gzip")
    reader = ArchiveReader(tmp_path)
    with pytest.raises(ArchiveDataError, match="failed to read"):
        reader.read_latest("daily", date(2026, 7, 31))


def test_read_trade_dates_filters_closed_days_and_requested_range(tmp_path):
    root = tmp_path / "normalized" / "trade_cal"
    root.mkdir(parents=True)
    (root / "20260803.csv").write_text(
        "cal_date,is_open\n"
        "20260730,1\n"
        "20260731,1\n"
        "20260801,0\n"
        "20260803,1\n",
        encoding="utf-8",
    )
    reader = ArchiveReader(tmp_path)
    assert reader.read_trade_dates(date(2026, 7, 31), date(2026, 8, 3)) == [
        "20260731",
        "20260803",
    ]


def test_read_recent_combines_only_latest_requested_partitions(tmp_path):
    root = tmp_path / "normalized" / "daily"
    root.mkdir(parents=True)
    for day, close in (("20260728", 10), ("20260729", 11), ("20260730", 12)):
        with gzip.open(root / f"{day}.csv.gz", "wt", encoding="utf-8") as handle:
            handle.write(
                f"ts_code,trade_date,close\n600000.SH,{day},{close}\n"
            )

    frame = ArchiveReader(tmp_path).read_recent(
        "daily",
        date(2026, 7, 30),
        2,
    )

    assert frame["trade_date"].astype(str).tolist() == ["20260729", "20260730"]
    assert frame["_archive_partition"].tolist() == ["20260729", "20260730"]


def test_read_static_requires_an_exact_candidate_name(tmp_path):
    root = tmp_path / "normalized" / "stock_basic"
    root.mkdir(parents=True)
    with gzip.open(root / "listed.csv.gz", "wt", encoding="utf-8") as handle:
        handle.write("ts_code\n600000.SH\n")
    with gzip.open(root / "unlisted.csv.gz", "wt", encoding="utf-8") as handle:
        handle.write("ts_code\n000001.SZ\n")

    frame = ArchiveReader(tmp_path).read_static(
        "stock_basic",
        ("listed.csv.gz",),
    )

    assert frame["ts_code"].tolist() == ["600000.SH"]


@pytest.mark.parametrize("partition_count", [0, -1])
def test_read_recent_rejects_non_positive_partition_count(
    tmp_path,
    partition_count,
):
    reader = ArchiveReader(tmp_path)

    with pytest.raises(ValueError, match="partition_count must be positive"):
        reader.read_recent("daily", date(2026, 7, 30), partition_count)


def test_read_static_rejects_candidate_paths_outside_dataset(tmp_path):
    normalized = tmp_path / "normalized"
    dataset_root = normalized / "stock_basic"
    dataset_root.mkdir(parents=True)
    (normalized / "secret.csv").write_text(
        "ts_code\n600000.SH\n",
        encoding="utf-8",
    )
    reader = ArchiveReader(tmp_path)

    with pytest.raises(ValueError, match="invalid static candidate name"):
        reader.read_static("stock_basic", ("../secret.csv",))
