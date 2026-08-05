"""Self-sustaining tail-decision domain model."""

from .config import DecisionConfig
from .contracts import (
    Allocation,
    Candidate,
    DecisionRun,
    DecisionStatus,
    InstrumentContext,
    InstrumentType,
    QualityDecision,
    QualityLevel,
    QuoteSnapshot,
)
from .recorder import DecisionRecorder
from .research_evidence import (
    ResearchEvidence,
    load_ai_discovery,
    load_uzi_evidence,
    merge_research_evidence,
)
from .funnel import CandidateFunnel, FunnelAudit, build_candidate_funnel
from .universe import (
    Universe,
    UniverseDataError,
    build_liquid_universe,
    load_universe_override,
)
from .workflow import TailDecisionWorkflow

__all__ = [
    "Allocation",
    "Candidate",
    "CandidateFunnel",
    "DecisionRun",
    "DecisionStatus",
    "FunnelAudit",
    "DecisionConfig",
    "DecisionRecorder",
    "InstrumentContext",
    "InstrumentType",
    "QualityDecision",
    "QualityLevel",
    "QuoteSnapshot",
    "ResearchEvidence",
    "TailDecisionWorkflow",
    "Universe",
    "UniverseDataError",
    "build_liquid_universe",
    "build_candidate_funnel",
    "load_universe_override",
    "load_ai_discovery",
    "load_uzi_evidence",
    "merge_research_evidence",
]
