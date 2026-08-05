from datetime import date
from pathlib import Path
import sys

import pandas as pd

SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision import (
    ResearchEvidence,
    Universe,
    build_candidate_funnel,
)


def empty_fund_daily() -> pd.DataFrame:
    return pd.DataFrame(columns=["ts_code", "trade_date", "close", "amount"])


def stock_codes(count: int) -> tuple[str, ...]:
    return tuple(f"{600000 + index:06d}.SH" for index in range(count))


def daily_for_codes(ids: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": instrument_id,
                "trade_date": trade_date.strftime("%Y%m%d"),
                "close": 10.0,
                "amount": 500_000.0,
            }
            for instrument_id in ids
            for trade_date in pd.date_range("2026-07-01", periods=20, freq="B")
        ]
    )


def test_ai_hint_can_raise_research_stock_into_top_30_observation_pool():
    universe = Universe(etfs=(), stocks=stock_codes(320))
    evidence = {"600319.SH": ResearchEvidence("600319.SH", ai_score=95.0)}

    funnel = build_candidate_funnel(
        universe,
        daily_for_codes(universe.stocks),
        empty_fund_daily(),
        evidence,
        as_of=date(2026, 7, 28),
        max_stocks=30,
        max_etfs=10,
    )

    assert len(funnel.research.stocks) == 320
    assert len(funnel.observation.stocks) == 30
    assert "600319.SH" in funnel.observation.stocks


def test_uzi_blocked_name_is_excluded_and_audited_without_blocking_others():
    evidence = {
        "600001.SH": ResearchEvidence(
            "600001.SH", uzi_score=90.0, uzi_state="blocked"
        )
    }

    funnel = build_candidate_funnel(
        Universe(etfs=(), stocks=("600001.SH", "600002.SH")),
        daily_for_codes(("600001.SH", "600002.SH")),
        empty_fund_daily(),
        evidence,
        as_of=date(2026, 7, 28),
        max_stocks=2,
        max_etfs=1,
    )

    assert funnel.observation.stocks == ("600002.SH",)
    assert "uzi_blocked:600001.SH" in funnel.audit.reasons


def test_observation_ties_are_ordered_by_instrument_id_and_etfs_are_capped():
    universe = Universe(
        etfs=("510300.SH", "510500.SH"),
        stocks=("600002.SH", "600001.SH"),
    )
    fund_daily = daily_for_codes(universe.etfs)

    funnel = build_candidate_funnel(
        universe,
        daily_for_codes(universe.stocks),
        fund_daily,
        {},
        as_of=date(2026, 7, 28),
        max_stocks=2,
        max_etfs=1,
    )

    assert funnel.observation.stocks == ("600001.SH", "600002.SH")
    assert funnel.observation.etfs == ("510300.SH",)


def test_future_daily_rows_cannot_change_observation_order():
    universe = Universe(etfs=(), stocks=("600001.SH", "600002.SH"))
    daily = pd.concat([
        daily_for_codes(universe.stocks),
        pd.DataFrame([{
            "ts_code": "600002.SH",
            "trade_date": "20260803",
            "close": 100.0,
            "amount": 50_000_000.0,
        }]),
    ], ignore_index=True)

    funnel = build_candidate_funnel(
        universe,
        daily,
        empty_fund_daily(),
        {},
        as_of=date(2026, 7, 28),
        max_stocks=1,
        max_etfs=1,
    )

    assert funnel.observation.stocks == ("600001.SH",)


def test_research_pool_shrinkage_is_audited_against_target():
    universe = Universe(etfs=(), stocks=("600001.SH", "600002.SH"))

    funnel = build_candidate_funnel(
        universe,
        daily_for_codes(universe.stocks),
        empty_fund_daily(),
        {},
        as_of=date(2026, 7, 28),
        max_stocks=2,
        max_etfs=1,
    )

    assert "research_stock_target_unmet:2/300" in funnel.audit.reasons


def test_non_finite_evidence_bonus_cannot_break_deterministic_ordering():
    universe = Universe(etfs=(), stocks=("600002.SH", "600001.SH"))
    evidence = {
        "600002.SH": ResearchEvidence(
            "600002.SH", ai_score=float("nan"), uzi_score=float("inf")
        )
    }

    funnel = build_candidate_funnel(
        universe,
        daily_for_codes(universe.stocks),
        empty_fund_daily(),
        evidence,
        as_of=date(2026, 7, 28),
        max_stocks=1,
        max_etfs=1,
    )

    assert funnel.observation.stocks == ("600001.SH",)
