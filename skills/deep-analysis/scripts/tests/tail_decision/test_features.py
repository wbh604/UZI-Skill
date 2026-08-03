from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pandas as pd

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.features import (
    build_historical_features,
    build_intraday_features,
)


def test_intraday_features_ignore_bars_after_as_of():
    bars = pd.DataFrame(
        [
            {
                "timestamp": "2026-08-03 14:00:00+08:00",
                "close": 10.0,
                "volume": 100,
                "amount": 1000,
            },
            {
                "timestamp": "2026-08-03 14:10:00+08:00",
                "close": 10.2,
                "volume": 100,
                "amount": 1020,
            },
            {
                "timestamp": "2026-08-03 14:11:00+08:00",
                "close": 20.0,
                "volume": 100,
                "amount": 2000,
            },
        ]
    )
    as_of = datetime(2026, 8, 3, 14, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
    result = build_intraday_features(bars, as_of)
    assert result["last_price"] == 10.2
    assert result["tail_return_pct"] == 2.0


def test_historical_features_use_latest_rows_and_fixed_windows():
    dates = pd.date_range("2026-07-06", periods=21, freq="D").strftime("%Y%m%d")
    daily = pd.DataFrame(
        {
            "ts_code": ["600406.SH"] * 21,
            "trade_date": dates,
            "close": list(range(10, 31)),
            "amount": list(range(100, 121)),
        }
    )
    daily_basic = pd.DataFrame(
        [
            {"ts_code": "600406.SH", "trade_date": dates[-1], "turnover_rate": 3.5}
        ]
    )
    moneyflow = pd.DataFrame(
        [
            {"ts_code": "600406.SH", "trade_date": dates[-1], "net_mf_amount": 500}
        ]
    )
    result = build_historical_features(daily, daily_basic, moneyflow)["600406.SH"]
    assert result["avg_amount_20d"] == 110.5
    assert result["return_5d_pct"] == 20.0
    assert result["return_20d_pct"] == 200.0
    assert result["recent_turnover_rate"] == 3.5
    assert result["net_mf_amount"] == 500.0
