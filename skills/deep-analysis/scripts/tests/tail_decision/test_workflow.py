from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.contracts import DecisionStatus
from lib.tail_decision.workflow import TailDecisionWorkflow
from .fixtures import workflow_dependencies


def test_workflow_does_not_turn_provider_failure_into_no_trade():
    workflow = TailDecisionWorkflow(
        **workflow_dependencies(all_providers_fail=True)
    )

    result = workflow.run(
        as_of="2026-08-03T14:10:00+08:00",
        phase="preview",
    )

    assert result.status is DecisionStatus.BLOCKED


def test_single_source_produces_watch_only_without_allocations():
    workflow = TailDecisionWorkflow(**workflow_dependencies(single_source=True))

    result = workflow.run(
        as_of="2026-08-03T14:10:00+08:00",
        phase="preview",
    )

    assert result.status is DecisionStatus.WATCH_ONLY
    assert result.allocations == ()


def test_final_phase_allocates_only_after_quality_passes():
    workflow = TailDecisionWorkflow(**workflow_dependencies())

    result = workflow.run(
        as_of="2026-08-03T14:30:00+08:00",
        phase="final",
    )

    assert result.status is DecisionStatus.RECOMMENDED
    assert 0 < sum(item.notional for item in result.allocations) <= 8_000.0


def test_passed_data_without_candidates_is_no_trade():
    workflow = TailDecisionWorkflow(**workflow_dependencies(no_candidates=True))

    result = workflow.run(
        as_of="2026-08-03T14:30:00+08:00",
        phase="final",
    )

    assert result.status is DecisionStatus.NO_TRADE
    assert result.allocations == ()
