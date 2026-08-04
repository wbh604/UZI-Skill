from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pandas as pd


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.config import DecisionConfig
from lib.tail_decision.contracts import InstrumentType, QualityLevel, QuoteSnapshot
from lib.tail_decision.event_risk import Announcement
from lib.tail_decision.gateway import CredentialFreeGateway
from lib.tail_decision.snapshot_store import QuoteSnapshotStore
from lib.tail_decision.universe import Universe


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 4, hour, minute, tzinfo=SHANGHAI)


class _Archive:
    def __init__(self):
        dates = pd.date_range("2026-07-06", periods=21, freq="D")
        self.stock_daily = pd.DataFrame(
            {
                "ts_code": ["600001.SH"] * len(dates),
                "trade_date": dates.strftime("%Y%m%d"),
                "close": [10.0 + index * 0.01 for index in range(len(dates))],
                "amount": [600_000.0] * len(dates),
            }
        )
        self.fund_daily = pd.DataFrame(
            {
                "ts_code": ["510300.SH"] * len(dates),
                "trade_date": dates.strftime("%Y%m%d"),
                "close": [1.0 + index * 0.001 for index in range(len(dates))],
                "amount": [800_000.0] * len(dates),
            }
        )

    def read_recent(self, dataset, as_of, partition_count, *, required=True):
        frames = {
            "daily": self.stock_daily,
            "fund_daily": self.fund_daily,
            "daily_basic": pd.DataFrame(
                [{"ts_code": "600001.SH", "trade_date": "20260726", "turnover_rate": 2.0}]
            ),
            "moneyflow": pd.DataFrame(
                [{"ts_code": "600001.SH", "trade_date": "20260726", "net_mf_amount": 10_000.0}]
            ),
        }
        frame = frames.get(dataset, pd.DataFrame())
        if required and frame.empty:
            raise RuntimeError(dataset)
        return frame.copy()

    def read_static(self, dataset, candidates, *, required=True):
        assert dataset == "stock_basic"
        return pd.DataFrame(
            [
                {
                    "ts_code": "600001.SH",
                    "name": "正常股份",
                    "industry": "电力设备",
                    "list_date": "20200101",
                }
            ]
        )

    def read_latest(self, dataset, as_of, *, required=True):
        frames = {
            "etf_basic": pd.DataFrame(
                [
                    {
                        "ts_code": "510300.SH",
                        "csname": "沪深300ETF",
                        "index_code": "000300.SH",
                        "list_status": "L",
                    }
                ]
            ),
            "stock_st": pd.DataFrame(columns=["ts_code", "name"]),
            "suspend_d": pd.DataFrame(columns=["ts_code", "suspend_type"]),
            "stk_limit": pd.DataFrame(
                [{"ts_code": "600001.SH", "up_limit": 11.2, "down_limit": 9.2}]
            ),
        }
        frame = frames.get(dataset, pd.DataFrame())
        if required and frame.empty:
            raise RuntimeError(dataset)
        return frame.copy()

    def read_trade_dates(self, start, end):
        return ["20260803", "20260804"]


class _QuoteProvider:
    def __init__(self, name: str, price_offset: float):
        self.name = name
        self.price_offset = price_offset

    def fetch_quotes(self, ids, now):
        step = 0.0 if now.minute == 0 else 0.02
        quotes = {}
        for instrument_id in ids:
            is_etf = instrument_id == "510300.SH"
            base = 1.2 if is_etf else 10.2
            price = base + step + self.price_offset
            quotes[instrument_id] = QuoteSnapshot(
                instrument_id=instrument_id,
                instrument_type=InstrumentType.ETF if is_etf else InstrumentType.STOCK,
                timestamp=now,
                last_price=price,
                open=base,
                high=price,
                low=base - 0.01,
                pre_close=base - 0.02,
                volume=100_000.0 + now.minute * 1_000.0,
                amount=10_000_000.0 + now.minute * 100_000.0,
                source=self.name,
                fetched_at=now,
            )
        return quotes


class _Announcements:
    def fetch(self, instrument_id, as_of):
        return (
            Announcement(
                "年度权益分派实施公告",
                as_of - timedelta(hours=1),
                "eastmoney",
            ),
        )


def _gateway(tmp_path, announcement_provider=None):
    return CredentialFreeGateway(
        config=DecisionConfig(),
        archive_reader=_Archive(),
        snapshot_store=QuoteSnapshotStore(tmp_path),
        quote_providers=(
            _QuoteProvider("eastmoney", 0.0),
            _QuoteProvider("tencent", 0.001),
        ),
        announcement_provider=announcement_provider or _Announcements(),
        universe_override=Universe(
            etfs=("510300.SH",),
            stocks=("600001.SH",),
        ),
    )


def test_gateway_builds_production_contexts_from_archive_and_forward_snapshots(tmp_path):
    gateway = _gateway(tmp_path)
    gateway.collect(as_of=_at(14), phase="warmup")

    inputs = gateway.collect(as_of=_at(14, 30), phase="final")

    assert [item.level for item in inputs.quality] == [
        QualityLevel.PASS,
        QualityLevel.PASS,
    ]
    stock = inputs.stock_contexts[0]
    assert stock.intraday["production_ready"] is True
    assert stock.historical["avg_amount_20d"] == 600_000_000.0
    assert stock.historical["net_mf_amount"] == 10_000_000.0
    assert stock.metadata["name"] == "正常股份"
    assert stock.metadata["limit_up"] == 11.2
    assert stock.events["event_status"] == "checked"
    assert stock.events["adverse_event"] is False

    etf = inputs.etf_contexts[0]
    assert etf.metadata["tracking_index"] == "000300.SH"
    assert etf.metadata["premium_proxy_source"] == "cross_source_price_deviation"
    assert 0 < etf.metadata["premium_proxy_pct"] < 0.3


class _BrokenAnnouncements:
    def fetch(self, instrument_id, as_of):
        raise TimeoutError("provider unavailable")


def test_gateway_treats_unknown_announcement_status_as_adverse(tmp_path):
    gateway = _gateway(tmp_path, _BrokenAnnouncements())

    inputs = gateway.collect(as_of=_at(14, 30), phase="final")

    assert inputs.stock_contexts[0].events == {
        "event_status": "unknown",
        "adverse_event": True,
        "risk_titles": (),
    }


class _PreviousDayProvider(_QuoteProvider):
    def fetch_quotes(self, ids, now):
        return {
            instrument_id: replace(
                item,
                timestamp=item.timestamp - timedelta(days=1),
            )
            for instrument_id, item in super().fetch_quotes(ids, now).items()
        }


def test_gateway_persists_mixed_quote_dates_without_cross_day_append_failure(tmp_path):
    gateway = CredentialFreeGateway(
        config=DecisionConfig(),
        archive_reader=_Archive(),
        snapshot_store=QuoteSnapshotStore(tmp_path),
        quote_providers=(
            _QuoteProvider("eastmoney", 0.0),
            _PreviousDayProvider("tencent", 0.001),
        ),
        announcement_provider=_Announcements(),
        universe_override=Universe(
            etfs=("510300.SH",),
            stocks=("600001.SH",),
        ),
    )

    inputs = gateway.collect(as_of=_at(14, 30), phase="final")

    assert len(inputs.quality) == 2
    snapshot_root = tmp_path / "cache" / "tail_decision" / "snapshots"
    assert (snapshot_root / "20260803.jsonl").is_file()
    assert (snapshot_root / "20260804.jsonl").is_file()
