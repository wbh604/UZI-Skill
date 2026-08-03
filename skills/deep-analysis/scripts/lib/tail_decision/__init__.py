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
from .workflow import TailDecisionWorkflow

__all__ = [
    "Allocation",
    "Candidate",
    "DecisionRun",
    "DecisionStatus",
    "DecisionConfig",
    "DecisionRecorder",
    "InstrumentContext",
    "InstrumentType",
    "QualityDecision",
    "QualityLevel",
    "QuoteSnapshot",
    "TailDecisionWorkflow",
]
