"""Definition quality judge — Layer 1 bounded rubric.

Compares a CampaignDefinition to the original prompt using 3-5 fixed
rubric questions (yes/no/unknown). Score = yes/total. STRICT default
threshold 1.0. Runs only after deterministic checks pass.

Catches structurally valid but semantically wrong definitions:
- objective fidelity
- seniority/geography capture
- no invented constraints
- query intents actionable
"""

from __future__ import annotations

from nirite.eval.models import (
    EvalFinding,
    EvalMode,
    EvalReport,
    EvalSeverity,
    FindingCode,
)
from nirite.judge.client import JudgeClient
from nirite.judge.models import JudgeAnswerValue, JudgePolarity, JudgeQuestion
from nirite.judge.scoring import score_verdict
from nirite.models.campaign import CampaignDefinition

QUALITY_RUBRIC_VERSION = "1"
STRICT_THRESHOLD = 1.0  # all questions must be yes in strict mode

QUALITY_QUESTIONS = [
    (
        "objective_fidelity",
        "Does the definition's objective match the user's original intent without adding or removing goals?",
    ),
    (
        "scope_capture",
        "Does the definition capture the key attributes (seniority, geography, industry) mentioned in the original prompt, without inventing new ones?",
    ),
    (
        "no_invented_constraints",
        "Does the definition avoid adding constraints, thresholds, or requirements not present in the original prompt?",
    ),
    (
        "query_actionable",
        "Are the generated search queries specific and actionable enough to retrieve relevant prospects?",
    ),
]


def _build_quality_questions() -> list[JudgeQuestion]:
    """Build the fixed set of quality rubric questions."""
    return [
        JudgeQuestion(
            id=f"q{i + 1}",
            text=text,
            criterion_id="quality",
            answerable_from=["original_prompt", "campaign_definition"],
            polarity=JudgePolarity.POSITIVE,
        )
        for i, (_, text) in enumerate(QUALITY_QUESTIONS)
    ]


def run_quality_eval(
    original_prompt: str,
    definition: CampaignDefinition,
    judge_client: JudgeClient,
) -> EvalReport:
    """Run the quality rubric judge on a campaign definition.

    Returns an EvalReport. In STRICT mode, any score < 1.0 produces an
    ERROR finding. Never raises — returns findings instead.
    """
    questions = _build_quality_questions()
    subject = {
        "original_prompt": original_prompt,
        "campaign_definition": definition.model_dump(mode="json"),
    }

    try:
        answers = judge_client.judge(questions, subject)
    except Exception as exc:  # noqa: BLE001 — judge unavailable → fail closed
        findings = [
            EvalFinding(
                check_id="check_quality_judge",
                code=FindingCode.QUALITY_RUBRIC_FAIL,
                severity=EvalSeverity.ERROR,
                message=f"quality judge unavailable: {exc}",
                path="quality",
            )
        ]
        return EvalReport(
            artifact="CampaignDefinition",
            mode=EvalMode.STRICT,
            findings=findings,
            checks_run=1,
        )

    score = score_verdict(questions, answers)
    passed = score >= STRICT_THRESHOLD

    findings: list[EvalFinding] = []
    if not passed:
        failed_questions = [
            q.id for q, a in zip(questions, answers) if a.answer != JudgeAnswerValue.YES
        ]
        findings.append(
            EvalFinding(
                check_id="check_quality_rubric",
                code=FindingCode.QUALITY_RUBRIC_FAIL,
                severity=EvalSeverity.ERROR,
                message=(
                    f"quality rubric score {score:.2f} below strict threshold "
                    f"{STRICT_THRESHOLD}; failed questions: {', '.join(failed_questions)}"
                ),
                path="quality",
                evidence=f"score={score:.2f}",
            )
        )

    return EvalReport(
        artifact="CampaignDefinition",
        mode=EvalMode.STRICT,
        findings=findings,
        checks_run=1,
    )
