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
