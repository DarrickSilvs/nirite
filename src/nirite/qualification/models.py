"""Qualification models — per-criterion and per-candidate verdicts with fail-closed aggregation.

Layer 3 turns Layer 2 ranked Candidates into qualified prospects. Each candidate
gets a per-criterion verdict (passed/failed/unknown) aggregated into an overall
verdict (qualified/not_qualified/bordered) using the policy in ``policy.py``.

This is a leaf module — it does not import from ``eval`` or ``retrieval``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CriterionStatus(StrEnum):
    """Per-criterion verdict status."""

    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class VerdictStatus(StrEnum):
    """Overall per-candidate qualification verdict."""

    QUALIFIED = "qualified"
    NOT_QUALIFIED = "not_qualified"
    BORDERED = "bordered"


class CriterionVerdict(BaseModel):
    """Verdict for a single criterion on a single candidate."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    criterion_id: str = Field(description="ID of the criterion being evaluated.")
    kind: str = Field(description="requirement, exclusion, or preference.")
    mode_used: str = Field(description="structured, semantic, or hybrid.")
    status: CriterionStatus = Field(description="passed, failed, or unknown.")
    score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Judge score for semantic/hybrid criteria; 1.0/0.0 for structured.",
    )
    evidence: str | None = Field(
        default=None,
        max_length=200,
        description="Short identifying string — never full prospect data.",
    )
    judge_answer_ids: list[str] = Field(
        default_factory=list,
        description="IDs of the judge answers that fed this verdict.",
    )


class CandidateVerdict(BaseModel):
    """Overall verdict for a single candidate across all criteria."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rank: int = Field(ge=1, description="Layer 2 RRF rank of the candidate.")
    prospect_hash: str = Field(
        description="SHA256 of prospect identifying fields — never full PII."
    )
    prospect_label: str = Field(
        description="Display label (name or company name) for CLI output."
    )
    status: VerdictStatus = Field(description="qualified, not_qualified, or bordered.")
    criterion_verdicts: list[CriterionVerdict] = Field(
        description="Per-criterion verdicts."
    )
    preference_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Aggregated preference score — never changes verdict, only tie-breaks.",
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Human-readable short reasons for the verdict.",
    )

    @model_validator(mode="after")
    def _validate_criterion_count(self) -> CandidateVerdict:
        """Each criterion must have exactly one verdict."""
        criterion_ids = [cv.criterion_id for cv in self.criterion_verdicts]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("duplicate criterion_id in criterion_verdicts")
        return self


class QualificationOutput(BaseModel):
    """Complete Layer 3 qualification output for one campaign."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    campaign_hash: str = Field(
        description="SHA256 of the campaign definition — audit trail."
    )
    judge_model: str = Field(description="Model used for semantic judging.")
    prompt_version: str = Field(description="Version of the judge prompt template.")
    verdicts: list[CandidateVerdict] = Field(
        description="Per-candidate verdicts, ordered by status then preference score."
    )
    counts: dict[str, int] = Field(
        default_factory=dict,
        description="Count of verdicts by status (qualified/not_qualified/bordered).",
    )

    @model_validator(mode="after")
    def _validate_counts_match_verdicts(self) -> QualificationOutput:
        """Counts must match verdicts."""
        tally: dict[str, int] = {}
        for v in self.verdicts:
            tally[v.status.value] = tally.get(v.status.value, 0) + 1
        for status_value, count in tally.items():
            if self.counts.get(status_value) != count:
                raise ValueError(
                    f"counts[{status_value!r}] = {self.counts.get(status_value)} "
                    f"but {count} verdicts have that status"
                )
        return self

    @property
    def qualified_count(self) -> int:
        return self.counts.get("qualified", 0)

    @property
    def not_qualified_count(self) -> int:
        return self.counts.get("not_qualified", 0)

    @property
    def bordered_count(self) -> int:
        return self.counts.get("bordered", 0)
