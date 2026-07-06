from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))


def test_capital_flow_score_uses_latest_five_records():
    """main_fund_flow_20d is oldest->newest; scoring must use the latest 5 rows."""
    from lib.pipeline.score_fns import score_dimensions

    flow = (
        [{"日期": f"2026-06-{day:02d}", "主力净流入-净额": 100_000_000} for day in range(1, 6)]
        + [{"日期": f"2026-06-{day:02d}", "主力净流入-净额": -100_000_000} for day in range(6, 11)]
    )
    raw = {
        "ticker": "600036.SH",
        "dimensions": {
            "12_capital_flow": {
                "data": {
                    "main_fund_flow_20d": flow,
                    "unlock_schedule": [],
                }
            }
        },
    }

    dim = score_dimensions(raw)["dimensions"]["12_capital_flow"]

    assert dim["score"] == 5
    assert dim["label"] == "主力 5日 -5.0亿 · 12 个月解禁 0 次"
    assert dim["reasons_fail"] == ["主力资金 5 日净流出 -5.0亿"]
