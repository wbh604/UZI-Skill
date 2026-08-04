from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.forward import ForwardJournal
from .fixtures import decision_run


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _events(index: int):
    kind = "etf" if index % 2 == 0 else "stock"
    pnl = -1.0 if index % 4 == 0 else 2.0
    evidence = [{"source": "eastmoney", "timestamp": "2026-08-04T14:30:00+08:00"}]
    return [
        {
            "kind": "paper_entry",
            "instrument_type": kind,
            "filled": True,
            "quote_sources": evidence,
        },
        {
            "kind": "paper_exit",
            "instrument_type": kind,
            "filled": True,
            "entry_notional": 3_000.0,
            "net_pnl": pnl,
            "quote_sources": evidence,
        },
    ]


def test_forward_gate_never_relaxes_the_sample_minimum(tmp_path):
    journal = ForwardJournal(tmp_path)
    start = datetime(2026, 8, 4, tzinfo=SHANGHAI)
    for index in range(59):
        day = start + timedelta(days=index)
        run = replace(
            decision_run(run_id=f"day-{index}_final"),
            as_of=day,
        )
        journal.record_day(
            run,
            _events(index) if index < 40 else [],
            is_trading_day=True,
        )

    assert journal.summary()["release_state"] == "collecting"
    last_day = start + timedelta(days=59)
    journal.record_day(
        replace(decision_run(run_id="day-59_final"), as_of=last_day),
        [],
        is_trading_day=True,
    )

    summary = journal.summary()
    assert summary["trading_days"] == 60
    assert summary["paper_entries"] == 40
    assert summary["release_state"] == "eligible"
    assert summary["formal_start_date"] == "2026-08-04"
    assert summary["snapshots_reconciled"] is True
    assert set(summary["by_instrument_type"]) == {"etf", "stock"}


def test_forward_gate_stays_collecting_without_forty_entries(tmp_path):
    journal = ForwardJournal(tmp_path)
    start = datetime(2026, 8, 4, tzinfo=SHANGHAI)
    for index in range(60):
        day = start + timedelta(days=index)
        journal.record_day(
            replace(decision_run(run_id=f"day-{index}_final"), as_of=day),
            _events(index) if index < 39 else [],
            is_trading_day=True,
        )

    summary = journal.summary()
    assert summary["trading_days"] == 60
    assert summary["paper_entries"] == 39
    assert summary["release_state"] == "collecting"


def test_forward_journal_records_blocked_non_trading_observations_once(tmp_path):
    journal = ForwardJournal(tmp_path)
    run = replace(
        decision_run(run_id="blocked-final"),
        as_of=datetime(2026, 8, 8, tzinfo=SHANGHAI),
    )

    first = journal.record_day(run, [], is_trading_day=False)
    second = journal.record_day(run, [], is_trading_day=False)

    assert first == second
    summary = journal.summary()
    assert summary["observations"] == 1
    assert summary["trading_days"] == 0
