from datetime import datetime
from pathlib import Path
import sys

from pandas.testing import assert_frame_equal

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.contracts import InstrumentType
from lib.tail_decision.features import build_intraday_features
from lib.tail_decision.snapshot_store import QuoteSnapshotStore
from .fixtures import quote


def _etf_quote(at, *, source="eastmoney", price=10.0, volume=1000, amount=10_000):
    return quote(
        instrument_id="510300.SH",
        instrument_type=InstrumentType.ETF,
        timestamp=at,
        fetched_at=at,
        last_price=price,
        open=9.9,
        high=max(10.1, price),
        low=min(9.8, price),
        pre_close=9.8,
        volume=volume,
        amount=amount,
        source=source,
    )


def test_snapshot_store_reconstructs_forward_intraday_deltas(tmp_path):
    store = QuoteSnapshotStore(tmp_path)
    at_1400 = datetime.fromisoformat("2026-08-04T14:00:00+08:00")
    at_1410 = datetime.fromisoformat("2026-08-04T14:10:00+08:00")
    store.append(
        phase="warmup",
        quotes={"510300.SH": [_etf_quote(at_1400)]},
    )
    store.append(
        phase="preview",
        quotes={
            "510300.SH": [
                _etf_quote(at_1410, price=10.2, volume=1300, amount=13_600)
            ]
        },
    )

    bars = store.read_intraday("510300.SH", at_1410)

    assert bars["volume"].tolist() == [1000.0, 300.0]
    assert bars["amount"].tolist() == [10_000.0, 3_600.0]
    assert bars["close"].tolist() == [10.0, 10.2]
    assert build_intraday_features(bars, at_1410)["production_ready"] is True


def test_snapshot_store_keeps_raw_retries_but_deduplicates_read_view(tmp_path):
    store = QuoteSnapshotStore(tmp_path)
    at_1410 = datetime.fromisoformat("2026-08-04T14:10:00+08:00")
    quotes = {
        "510300.SH": [
            _etf_quote(at_1410, source="tencent", price=10.1),
            _etf_quote(at_1410, source="eastmoney", price=10.2),
        ]
    }
    path = store.append(phase="preview", quotes=quotes)
    store.append(phase="preview", quotes=quotes)

    bars = store.read_intraday("510300.SH", at_1410)

    assert len(path.read_text(encoding="utf-8").splitlines()) == 4
    assert bars["close"].tolist() == [10.2]
    assert bars["source"].tolist() == ["eastmoney"]


def test_snapshot_store_treats_counter_reset_as_a_new_baseline(tmp_path):
    store = QuoteSnapshotStore(tmp_path)
    times = [
        datetime.fromisoformat(value)
        for value in (
            "2026-08-04T14:00:00+08:00",
            "2026-08-04T14:10:00+08:00",
            "2026-08-04T14:20:00+08:00",
        )
    ]
    counters = ((1000, 10_000), (1300, 13_600), (100, 1_200))
    for at, (volume, amount) in zip(times, counters, strict=True):
        store.append(
            phase="preview",
            quotes={
                "510300.SH": [
                    _etf_quote(at, volume=volume, amount=amount)
                ]
            },
        )

    bars = store.read_intraday("510300.SH", times[-1])

    assert bars["volume"].tolist() == [1000.0, 300.0, 100.0]
    assert bars["amount"].tolist() == [10_000.0, 3_600.0, 1_200.0]


def test_snapshot_store_excludes_records_after_as_of(tmp_path):
    store = QuoteSnapshotStore(tmp_path)
    at_1410 = datetime.fromisoformat("2026-08-04T14:10:00+08:00")
    at_1420 = datetime.fromisoformat("2026-08-04T14:20:00+08:00")
    store.append(
        phase="preview",
        quotes={"510300.SH": [_etf_quote(at_1410, price=10.1)]},
    )
    store.append(
        phase="final",
        quotes={"510300.SH": [_etf_quote(at_1420, price=20.0)]},
    )

    first_read = store.read_intraday("510300.SH", at_1410)
    second_read = store.read_intraday("510300.SH", at_1410)

    assert first_read["close"].tolist() == [10.1]
    assert_frame_equal(second_read, first_read)
