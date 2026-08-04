from dataclasses import replace
from datetime import datetime
from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.contracts import DecisionStatus, QualityDecision, QualityLevel
from lib.tail_decision.phase_ledger import PhaseLedger
from .fixtures import candidate, decision_run, quote


def _final_run():
    base = decision_run(run_id="20260804T143000_final")
    stock_candidate = candidate(
        "600406.SH", kind="stock", price=25.0, lot_size=100, score=82
    )
    allocation = replace(
        base.allocations[-1],
        instrument_id="600406.SH",
        quantity=100,
        limit_price=25.0,
        notional=2_500.0,
        candidate_score=82.0,
    )
    return replace(
        base,
        as_of=datetime.fromisoformat("2026-08-04T14:30:00+08:00"),
        etf_candidates=(),
        stock_candidates=(stock_candidate,),
        allocations=(allocation,),
    )


def _phase_run(phase, as_of, price):
    instant = datetime.fromisoformat(as_of)
    first = quote(
        timestamp=instant,
        fetched_at=instant,
        last_price=price,
        source="eastmoney",
    )
    second = quote(
        timestamp=instant,
        fetched_at=instant,
        last_price=price,
        source="tencent",
    )
    quality = QualityDecision(
        instrument_id="600406.SH",
        level=QualityLevel.PASS,
        reasons=(),
        canonical_quote=first,
        source_quotes=(first, second),
    )
    return replace(
        decision_run(run_id=f"{instant.strftime('%Y%m%dT%H%M%S')}_{phase}"),
        as_of=instant,
        status=DecisionStatus.NO_TRADE,
        quality=(quality,),
        etf_candidates=(),
        stock_candidates=(),
        allocations=(),
        reasons=(f"{phase}_completed",),
    )


def test_phase_ledger_replays_plan_entry_signal_and_exit(tmp_path):
    ledger = PhaseLedger(tmp_path)
    ledger.advance(phase="final", run=_final_run())
    ledger.advance(
        phase="close",
        run=_phase_run("close", "2026-08-04T15:05:00+08:00", 24.98),
    )

    next_open = datetime.fromisoformat("2026-08-05T09:25:00+08:00")
    assert ledger.current_positions(as_of=next_open).keys() == {"600406.SH"}
    ledger.advance(
        phase="exit_open",
        run=_phase_run("exit_open", "2026-08-05T09:25:00+08:00", 25.40),
    )
    ledger.advance(
        phase="exit_check",
        run=_phase_run("exit_check", "2026-08-05T09:35:00+08:00", 25.30),
    )

    assert ledger.current_positions(
        as_of=datetime.fromisoformat("2026-08-05T09:35:00+08:00")
    ) == {}
    assert [row["kind"] for row in ledger.read_events()] == [
        "plan_created",
        "paper_entry",
        "exit_signal",
        "paper_exit",
    ]
    exit_event = ledger.read_events()[-1]
    assert exit_event["net_pnl"] < exit_event["gross_pnl"]


def test_phase_ledger_retry_is_idempotent(tmp_path):
    ledger = PhaseLedger(tmp_path)
    run = _final_run()

    first = ledger.advance(phase="final", run=run)
    second = ledger.advance(phase="final", run=run)

    assert len(first) == 1
    assert second == ()
    assert len(ledger.read_events()) == 1


def test_phase_ledger_blocks_same_day_stock_exit(tmp_path):
    ledger = PhaseLedger(tmp_path)
    ledger.advance(phase="final", run=_final_run())
    ledger.advance(
        phase="close",
        run=_phase_run("close", "2026-08-04T15:05:00+08:00", 24.98),
    )

    events = ledger.advance(
        phase="exit_check",
        run=_phase_run("exit_check", "2026-08-04T15:10:00+08:00", 25.30),
    )

    assert events[0]["kind"] == "paper_exit_blocked"
    assert events[0]["block_reason"] == "stock_t_plus_one"
    assert "600406.SH" in ledger.current_positions(
        as_of=datetime.fromisoformat("2026-08-04T15:10:00+08:00")
    )
