from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def test_all_market_detail_fallback_when_stock_dates_empty():
    """If per-stock LHB dates are empty, fall back to all-market summary and filter by code."""
    from lib import data_sources as ds
    from lib.market_router import parse_ticker

    ti = parse_ticker("000004.SZ")
    recent = datetime.now().strftime("%Y-%m-%d")
    all_market = pd.DataFrame([
        {"代码": "000004", "名称": "国华退", "上榜日": recent, "龙虎榜净买额": 481476.41, "上榜原因": "退市整理期"},
        {"代码": "600036", "名称": "招商银行", "上榜日": recent, "龙虎榜净买额": 1.0, "上榜原因": "should filter out"},
    ])

    with patch.object(ds.ak, "stock_lhb_stock_detail_date_em", return_value=pd.DataFrame()), \
         patch.object(ds.ak, "stock_lhb_detail_em", return_value=all_market) as m_detail:
        records = ds._fetch_lhb_impl(ti, days=30)

    assert m_detail.called
    assert len(records) == 1
    assert records[0]["代码"] == "000004"
