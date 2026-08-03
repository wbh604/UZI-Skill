from pathlib import Path
import sys

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision import (
    Universe,
    UniverseDataError,
    build_liquid_universe,
    load_universe_override,
)


def test_universe_normalizes_liquidity_and_excludes_risky_masters():
    stock_daily = pd.DataFrame(
        [
            {"ts_code": "600001.SH", "trade_date": "20260729", "amount": 500_000},
            {"ts_code": "600001.SH", "trade_date": "20260730", "amount": 700_000},
            {"ts_code": "600002.SH", "trade_date": "20260730", "amount": 900_000},
            {"ts_code": "600003.SH", "trade_date": "20260730", "amount": 1_000_000},
            {"ts_code": "600004.SH", "trade_date": "20260730", "amount": 100_000},
        ]
    )
    stock_basic = pd.DataFrame(
        [
            {"ts_code": "600001.SH", "name": "正常股份", "list_date": "20100101"},
            {"ts_code": "600002.SH", "name": "*ST风险", "list_date": "20100101"},
            {"ts_code": "600003.SH", "name": "近期上市", "list_date": "20260720"},
            {"ts_code": "600004.SH", "name": "低流动性", "list_date": "20100101"},
        ]
    )
    fund_daily = pd.DataFrame(
        [
            {"ts_code": "510300.SH", "trade_date": "20260730", "amount": 800_000},
            {"ts_code": "159999.SZ", "trade_date": "20260730", "amount": 30_000},
        ]
    )
    etf_basic = pd.DataFrame(
        [
            {"ts_code": "510300.SH", "list_status": "L", "index_name": "沪深300"},
            {"ts_code": "159999.SZ", "list_status": "L", "index_name": "测试指数"},
        ]
    )

    universe = build_liquid_universe(
        stock_daily,
        fund_daily,
        stock_basic,
        etf_basic,
        min_stock_amount_cny=300_000_000.0,
        min_etf_amount_cny=50_000_000.0,
    )

    assert universe.stocks == ("600001.SH",)
    assert universe.etfs == ("510300.SH",)
    assert isinstance(universe, Universe)


def test_universe_order_is_stable_for_equal_liquidity():
    stock_daily = pd.DataFrame(
        [
            {"ts_code": "600010.SH", "trade_date": "20260730", "amount": 400_000},
            {"ts_code": "600001.SH", "trade_date": "20260730", "amount": 400_000},
        ]
    )
    stock_basic = pd.DataFrame(
        [
            {"ts_code": "600010.SH", "name": "股票十", "list_date": "20100101"},
            {"ts_code": "600001.SH", "name": "股票一", "list_date": "20100101"},
        ]
    )
    empty = pd.DataFrame(columns=["ts_code", "trade_date", "amount"])
    etf_basic = pd.DataFrame(columns=["ts_code", "list_status"])

    first = build_liquid_universe(stock_daily, empty, stock_basic, etf_basic)
    shuffled = build_liquid_universe(
        stock_daily.sample(frac=1.0, random_state=7),
        empty,
        stock_basic.sample(frac=1.0, random_state=9),
        etf_basic,
    )

    assert first.stocks == ("600001.SH", "600010.SH")
    assert shuffled == first


def test_universe_ignores_turnover_older_than_twenty_sessions():
    rows = [
        {"ts_code": "600001.SH", "trade_date": "20260601", "amount": 10_000_000}
    ]
    for day in pd.date_range("2026-07-01", periods=20, freq="D"):
        trade_date = day.strftime("%Y%m%d")
        rows.extend(
            [
                {"ts_code": "600001.SH", "trade_date": trade_date, "amount": 100_000},
                {"ts_code": "600002.SH", "trade_date": trade_date, "amount": 200_000},
            ]
        )
    stock_basic = pd.DataFrame(
        [
            {"ts_code": "600001.SH", "name": "股票一", "list_date": "20100101"},
            {"ts_code": "600002.SH", "name": "股票二", "list_date": "20100101"},
        ]
    )

    universe = build_liquid_universe(
        pd.DataFrame(rows),
        pd.DataFrame(columns=["ts_code", "trade_date", "amount"]),
        stock_basic,
        pd.DataFrame(columns=["ts_code", "list_status"]),
        max_stocks=1,
    )

    assert universe.stocks == ("600002.SH",)


def test_universe_override_preserves_order_and_rejects_empty_payload(tmp_path):
    path = tmp_path / "tail_decision_universe.json"
    assert load_universe_override(path) is None
    path.write_text(
        '{"etfs":["510300.SH","159915.SZ","510300.SH"],'
        '"stocks":["600001.SH"]}',
        encoding="utf-8",
    )

    universe = load_universe_override(path)

    assert universe.etfs == ("510300.SH", "159915.SZ")
    assert universe.stocks == ("600001.SH",)
    path.write_text('{"etfs":[],"stocks":[]}', encoding="utf-8")
    with pytest.raises(UniverseDataError, match="must contain at least one instrument"):
        load_universe_override(path)


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        '{"etfs":"510300.SH","stocks":[]}',
        '{"etfs":["510300"],"stocks":[]}',
    ],
)
def test_universe_override_rejects_malformed_payload(tmp_path, payload):
    path = tmp_path / "tail_decision_universe.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(UniverseDataError, match="invalid universe override"):
        load_universe_override(path)
