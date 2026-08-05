from dataclasses import replace
from datetime import datetime, timedelta
import json
import os
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


def broad_archive(stock_count=320):
    archive = _Archive()
    dates = pd.date_range("2026-07-06", periods=20, freq="B")
    stock_ids = tuple(f"{600000 + index:06d}.SH" for index in range(stock_count))
    archive.stock_daily = pd.DataFrame([
        {
            "ts_code": instrument_id,
            "trade_date": trade_date.strftime("%Y%m%d"),
            "close": 10.0,
            "amount": 600_000.0,
        }
        for instrument_id in stock_ids
        for trade_date in dates
    ])
    archive.stock_basic = pd.DataFrame([
        {
            "ts_code": instrument_id,
            "name": f"Name {index}",
            "industry": "fixture",
            "list_date": "20200101",
        }
        for index, instrument_id in enumerate(stock_ids)
    ])
    original_read_recent = archive.read_recent
    original_read_static = archive.read_static

    def read_recent(dataset, as_of, partition_count, *, required=True):
        if dataset == "daily_basic":
            return pd.DataFrame([
                {"ts_code": instrument_id, "trade_date": "20260731", "turnover_rate": 2.0}
                for instrument_id in stock_ids
            ])
        if dataset == "moneyflow":
            return pd.DataFrame([
                {"ts_code": instrument_id, "trade_date": "20260731", "net_mf_amount": 10_000.0}
                for instrument_id in stock_ids
            ])
        return original_read_recent(dataset, as_of, partition_count, required=required)

    def read_static(dataset, candidates, *, required=True):
        if dataset == "stock_basic":
            return archive.stock_basic.copy()
        return original_read_static(dataset, candidates, required=required)

    archive.read_recent = read_recent
    archive.read_static = read_static
    return archive


def multi_etf_archive(stock_count=320, etf_count=12):
    archive = broad_archive(stock_count)
    etf_ids = tuple(f"{510300 + index:06d}.SH" for index in range(etf_count))
    dates = pd.date_range("2026-07-06", periods=20, freq="B")
    archive.fund_daily = pd.DataFrame([
        {
            "ts_code": instrument_id,
            "trade_date": trade_date.strftime("%Y%m%d"),
            "close": 1.2,
            "amount": 800_000.0,
        }
        for instrument_id in etf_ids
        for trade_date in dates
    ])
    original_read_latest = archive.read_latest

    def read_latest(dataset, as_of, *, required=True):
        if dataset == "etf_basic":
            return pd.DataFrame([
                {
                    "ts_code": instrument_id,
                    "csname": f"ETF {index}",
                    "index_code": f"000{index:03d}.SH",
                    "list_status": "L",
                }
                for index, instrument_id in enumerate(etf_ids)
            ])
        return original_read_latest(dataset, as_of, required=required)

    archive.read_latest = read_latest
    return archive, set(archive.stock_basic["ts_code"]), set(etf_ids)


class _QuoteProvider:
    def __init__(self, name: str, price_offset: float, etf_ids=("510300.SH",)):
        self.name = name
        self.price_offset = price_offset
        self.etf_ids = frozenset(etf_ids)

    def fetch_quotes(self, ids, now):
        step = 0.0 if now.minute == 0 else 0.02
        quotes = {}
        for instrument_id in ids:
            is_etf = instrument_id in self.etf_ids
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


class RecordingQuoteProvider(_QuoteProvider):
    def __init__(self, name="eastmoney", price_offset=0.0, etf_ids=("510300.SH",)):
        super().__init__(name, price_offset, etf_ids)
        self.requested_ids = ()

    def fetch_quotes(self, ids, now):
        self.requested_ids = tuple(ids)
        return super().fetch_quotes(ids, now)


class MatchingQuoteProvider(_QuoteProvider):
    def __init__(self, etf_ids=("510300.SH",)):
        super().__init__("tencent", 0.001, etf_ids)


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


def production_gateway(
    tmp_path,
    *,
    archive=None,
    providers=None,
    research_root=None,
    uzi_cache_root=None,
):
    return CredentialFreeGateway(
        config=DecisionConfig(),
        archive_reader=archive or _Archive(),
        snapshot_store=QuoteSnapshotStore(tmp_path),
        quote_providers=providers or (_QuoteProvider("eastmoney", 0.0), MatchingQuoteProvider()),
        announcement_provider=_Announcements(),
        research_root=research_root,
        uzi_cache_root=uzi_cache_root,
    )


def write_uzi_cache(root, instrument_id, *, overall_score=71.0, blocked=False, malformed=False):
    cache = root / instrument_id
    cache.mkdir(parents=True)
    source = cache / "synthesis.json"
    source.write_text(
        "not-json" if malformed else json.dumps({
            "ticker": instrument_id,
            "overall_score": overall_score,
            "data_coverage": 0.70,
            "uzi_decision_state": "blocked" if blocked else "approved",
        }),
        encoding="utf-8",
    )
    timestamp = _at(12).timestamp()
    os.utime(source, (timestamp, timestamp))


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


def test_gateway_quotes_only_observation_pool_and_audits_research_count(tmp_path):
    archive = broad_archive(stock_count=320)
    provider = RecordingQuoteProvider()
    inputs = production_gateway(
        tmp_path,
        archive=archive,
        providers=(provider, MatchingQuoteProvider()),
    ).collect(as_of=_at(14, 10), phase="preview")

    assert inputs.raw_quotes["funnel_audit"]["research_stocks"] >= 300
    assert inputs.raw_quotes["funnel_audit"]["observation_stocks"] == 30
    assert len([item for item in provider.requested_ids if item.endswith((".SH", ".SZ")) and not item.startswith(("510", "159"))]) <= 30


def test_gateway_requests_type_specific_observation_limits_for_multi_etf_archive(tmp_path):
    archive, stock_ids, etf_ids = multi_etf_archive()
    provider = RecordingQuoteProvider(etf_ids=etf_ids)
    matching = RecordingQuoteProvider("tencent", 0.001, etf_ids)

    production_gateway(
        tmp_path,
        archive=archive,
        providers=(provider, matching),
    ).collect(as_of=_at(14, 10), phase="preview")

    requested = set(provider.requested_ids)
    assert matching.requested_ids == provider.requested_ids
    assert len(requested & stock_ids) <= 30
    assert len(requested & etf_ids) <= 10
    assert requested <= stock_ids | etf_ids


def test_gateway_passes_aware_as_of_to_funnel(monkeypatch, tmp_path):
    import lib.tail_decision.gateway as gateway_module

    observed = []
    real_builder = gateway_module.build_candidate_funnel

    def recording_builder(*args, **kwargs):
        observed.append(kwargs["as_of"])
        return real_builder(*args, **kwargs)

    monkeypatch.setattr(gateway_module, "build_candidate_funnel", recording_builder)
    as_of = _at(14, 10)
    production_gateway(tmp_path, archive=broad_archive()).collect(as_of=as_of, phase="preview")

    assert observed == [as_of]


def test_gateway_attaches_compact_fresh_evidence_and_excludes_blocked_name(tmp_path):
    research_root = tmp_path / "research"
    research_root.mkdir()
    (research_root / "weekly_candidates_20260804.json").write_text(json.dumps({
        "as_of": "2026-08-04",
        "candidates": [{"code": "600001.SH", "score": 82.0}],
        "review_queue": [],
    }), encoding="utf-8")
    uzi_root = tmp_path / "uzi"
    write_uzi_cache(uzi_root, "600001.SH")
    write_uzi_cache(uzi_root, "600002.SH", blocked=True)
    archive = broad_archive(stock_count=320)
    inputs = production_gateway(
        tmp_path,
        archive=archive,
        research_root=research_root,
        uzi_cache_root=uzi_root,
    ).collect(as_of=_at(14, 30), phase="final")

    stock = next(item for item in inputs.stock_contexts if item.instrument_id == "600001.SH")
    evidence = stock.metadata["research_evidence"]
    assert evidence["ai_score"] == 82.0
    assert evidence["uzi_score"] == 71.0
    assert evidence["uzi_state"] == "approved"
    assert stock.quote.timestamp == _at(14, 30)
    assert "600002.SH" not in [item.instrument_id for item in inputs.stock_contexts]
    assert inputs.raw_quotes["research_evidence"]["600002.SH"]["uzi_state"] == "blocked"
    assert "synthesis.json" in " ".join(evidence["source_paths"])


def test_gateway_isolates_missing_and_malformed_evidence_per_instrument(tmp_path):
    uzi_root = tmp_path / "uzi"
    write_uzi_cache(uzi_root, "600001.SH", malformed=True)
    inputs = production_gateway(
        tmp_path,
        archive=broad_archive(stock_count=320),
        uzi_cache_root=uzi_root,
    ).collect(as_of=_at(14, 10), phase="preview")

    by_id = {item.instrument_id: item for item in inputs.stock_contexts}
    assert by_id["600001.SH"].metadata["research_evidence"]["uzi_state"] == "unavailable"
    assert "uzi_invalid_json" in by_id["600001.SH"].metadata["research_evidence"]["reasons"]
    assert by_id["600002.SH"].metadata["research_evidence"]["reasons"] == ("uzi_missing",)
