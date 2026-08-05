from pathlib import Path
import sys


SCRIPTS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

from lib.tail_decision.contracts import DecisionStatus, QualityDecision, QualityLevel
from lib.tail_decision.workflow import TailDecisionWorkflow, WorkflowInputs
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
    assert 0 < sum(item.notional for item in result.allocations) <= 12_000.0


def test_final_phase_blocks_before_strategy_when_available_cash_is_missing():
    dependencies = workflow_dependencies()
    dependencies["config"] = dependencies["config"].__class__(available_cash_cny=None)
    workflow = TailDecisionWorkflow(**dependencies)

    result = workflow.run(
        as_of="2026-08-03T14:30:00+08:00",
        phase="final",
    )

    assert result.status is DecisionStatus.BLOCKED
    assert result.allocations == ()
    assert result.reasons == ("available_cash_missing",)


def test_passed_data_without_candidates_is_no_trade():
    workflow = TailDecisionWorkflow(**workflow_dependencies(no_candidates=True))

    result = workflow.run(
        as_of="2026-08-03T14:30:00+08:00",
        phase="final",
    )

    assert result.status is DecisionStatus.NO_TRADE
    assert result.allocations == ()


def test_one_unquoted_instrument_does_not_block_other_passed_candidates():
    dependencies = workflow_dependencies()
    base_gateway = dependencies["gateway"]

    class PartialFailureGateway:
        def collect(self, *, as_of, phase):
            inputs = base_gateway.collect(as_of=as_of, phase=phase)
            missing = QualityDecision(
                instrument_id="513310.SH",
                level=QualityLevel.BLOCKED,
                reasons=("no_valid_quotes",),
                canonical_quote=None,
                source_quotes=(),
            )
            return WorkflowInputs(
                system_errors=inputs.system_errors,
                quality=(*inputs.quality, missing),
                etf_contexts=inputs.etf_contexts,
                stock_contexts=inputs.stock_contexts,
                raw_quotes=inputs.raw_quotes,
            )

    dependencies["gateway"] = PartialFailureGateway()
    workflow = TailDecisionWorkflow(**dependencies)

    result = workflow.run(
        as_of="2026-08-03T14:30:00+08:00",
        phase="final",
    )

    assert result.status is DecisionStatus.RECOMMENDED
    assert result.allocations
