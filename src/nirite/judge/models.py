"""Shared bounded-judge models — one package reused by Layer 1 eval and Layer 3 qualification.

Defines the question/answer/verdict types. No thresholds here — policy lives
with callers. Scoring logic lives in ``scoring.py``. This is a leaf module:
it does not import from ``eval`` or ``qualification``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JudgeAnswerValue(StrEnum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class JudgePolarity(StrEnum):
    POSITIVE = "positive"  # yes means criterion met
    NEGATIVE = "negative"  # yes means criterion NOT met (exclusion)


class JudgeQuestion(BaseModel):
    """A single bounded yes/no/unknown question for the judge."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(description="Stable question id, e.g. 'c1.q1'.")
    text: str = Field(description="The question text presented to the judge.")
    criterion_id: str = Field(
        description="ID of the criterion this question evaluates."
    )
    answerable_from: list[str] = Field(
        default_factory=list,
        description="Field names the answer can be derived from (audit trail).",
    )
    polarity: JudgePolarity = Field(
        default=JudgePolarity.POSITIVE,
        description="POSITIVE: yes means met. NEGATIVE: yes means not met (exclusion).",
    )


class JudgeAnswer(BaseModel):
    """The judge's answer to a single question."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question_id: str = Field(description="Id of the question this answers.")
    answer: JudgeAnswerValue = Field(description="yes, no, or unknown.")
    evidence_field: str | None = Field(
        default=None, description="The prospect field the answer was based on."
    )
    evidence_quote: str | None = Field(
        default=None,
        max_length=200,
        description="Short quote from the prospect record — never a full blob.",
    )


class JudgeVerdict(BaseModel):
    """Aggregated verdict for a set of questions about one criterion or artifact.

    ``score`` is computed by ``scoring.score_verdict`` — fixed math,
    not set by the judge.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    criterion_id: str | None = Field(
        default=None,
        description="Criterion this verdict applies to, or None for artifact-level.",
    )
    answers: list[JudgeAnswer] = Field(
        default_factory=list, description="All answers, one per question."
    )
    score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fixed score = yes_count / total_questions. unknown counts as non-yes.",
    )
    rationale_code: str | None = Field(
        default=None, description="Short code explaining the verdict rationale."
    )
