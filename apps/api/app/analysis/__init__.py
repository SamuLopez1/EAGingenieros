"""Grafo de análisis: de documentos a requisitos con evidencia."""

from app.analysis.extractors import (
    ModelExtractor,
    RequirementExtractor,
    RuleBasedExtractor,
    guess_category,
    is_obligation,
)
from app.analysis.graph import AnalysisDependencies, build_analysis_graph
from app.analysis.nodes import (
    build_draft_summary,
    decide_state,
    node_validate_citations,
    normalise,
    quote_matches,
)
from app.analysis.state import (
    AnalysisError,
    AnalysisState,
    EvidenceMatch,
    NodeName,
    RequirementCandidate,
    StepRecord,
    StepStatus,
    ValidatedRequirement,
)

__all__ = [
    "AnalysisDependencies",
    "AnalysisError",
    "AnalysisState",
    "EvidenceMatch",
    "ModelExtractor",
    "NodeName",
    "RequirementCandidate",
    "RequirementExtractor",
    "RuleBasedExtractor",
    "StepRecord",
    "StepStatus",
    "ValidatedRequirement",
    "build_analysis_graph",
    "build_draft_summary",
    "decide_state",
    "guess_category",
    "is_obligation",
    "node_validate_citations",
    "normalise",
    "quote_matches",
]
