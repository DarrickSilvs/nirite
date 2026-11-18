"""Eval layer for Nirite — deterministic checks and bounded-judge results.

Provides typed vocabulary for eval results (Pydantic as source of truth):
``EvalSeverity``, ``EvalMode``, ``FindingCode``, ``EvalFinding``, and
``EvalReport``. This module is a leaf — it does not import from ``retrieval``
or ``campaign``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EvalSeverity(StrEnum):
    """Severity of an eval finding."""

    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class EvalMode(StrEnum):
    """Evaluation mode — STRICT fails closed, LENIENT only warns."""

    STRICT = "strict"
    LENIENT = "lenient"


class FindingCode(StrEnum):
    """Stable codes for every eval invariant, so tests assert on code not text."""

    # Structural checks on CampaignDefinition
    SCHEMA_INVALID = "schema_invalid"
    DUPLICATE_CRITERION_ID = "duplicate_criterion_id"
    DUPLICATE_QUERY_ID = "duplicate_query_id"
    QUERY_COUNT_OUT_OF_RANGE = "query_count_out_of_range"
    EMPTY_QUERY_TEXT = "empty_query_text"
    DUPLICATE_QUERY_TEXT = "duplicate_query_text"
    WEIGHT_ON_NON_PREFERENCE = "weight_on_non_preference"
    STRUCTURED_WITHOUT_PREDICATE = "structured_without_predicate"
    SEMANTIC_WITH_PREDICATE = "semantic_with_predicate"
    CLARIFICATION_REFERENCES_UNKNOWN = "clarification_references_unknown"
    NEEDS_CLARIFICATION_INCOHERENT = "needs_clarification_incoherent"

    # Cross-artifact consistency (analysis vs definition)
    CRITERION_DROPPED = "criterion_dropped"
    CRITERION_INVENTED = "criterion_invented"
    CRITERION_KIND_FLIPPED = "criterion_kind_flipped"
    CRITERION_FACET_UNCOVERED = "criterion_facet_uncovered"
    CONTRADICTORY_PREDICATES = "contradictory_predicates"
    TARGET_TYPE_MISMATCH = "target_type_mismatch"

    # Layer 3 qualification
    JUDGE_ERROR = "judge_error"
    JUDGE_CALL_CAP_EXCEEDED = "judge_call_cap_exceeded"

    # Quality judge
    QUALITY_RUBRIC_FAIL = "quality_rubric_fail"


class EvalFinding(BaseModel):
    """A single eval finding — code, severity, and short evidence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    check_id: str = Field(
        description="Stable identifier of the check that produced this finding."
    )
    code: FindingCode = Field(description="Stable code for the invariant that failed.")
    severity: EvalSeverity = Field(description="INFO, WARN, or ERROR.")
    message: str = Field(description="Human-readable explanation of the finding.")
    path: str | None = Field(
        default=None,
        description="Dotted path to the offending field (e.g. 'spec.criteria[2]').",
    )
    evidence: str | None = Field(
        default=None,
        description="Short identifying strings only (ids, field names) — never "
        "full prompts or prospect data.",
    )


class EvalReport(BaseModel):
    """Aggregated result of running one or more eval checks."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    artifact: str = Field(
        description="Name of the artifact evaluated (e.g. 'CampaignDefinition')."
    )
    mode: EvalMode = Field(description="STRICT or LENIENT.")
    findings: list[EvalFinding] = Field(
        default_factory=list, description="All findings, ordered by check execution."
    )
    checks_run: int = Field(default=0, ge=0, description="Number of checks executed.")

    @property
    def passed(self) -> bool:
        """True when no ERROR-severity findings exist."""
        return not any(f.severity == EvalSeverity.ERROR for f in self.findings)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == EvalSeverity.ERROR)

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == EvalSeverity.WARN)

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == EvalSeverity.INFO)
