"""Qualifier orchestrator — per candidate × per criterion verdicts with fail-closed aggregation.

Layer 3 turns Layer 2 ranked Candidates into qualified prospects:
1. Run structured checks first (zero LLM) using Criterion predicates —
   short-circuit on requirement failure or exclusion match without any LLM call.
2. Pool remaining semantic/hybrid questions per candidate into one batched
   judge call.
3. Aggregate via policy; compute preference score separately (never changes
   verdict, only tie-breaks).
4. Order qualified > bordered > not_qualified, tie-break on preference score
   then RRF score.

JudgeError propagates (no partial output). Needs_clarification definitions
rejected up front.
"""

from __future__ import annotations

from nirite.judge.client import JudgeClient
from nirite.judge.models import JudgeQuestion
from nirite.judge.scoring import score_verdict
from nirite.models.campaign import CampaignDefinition
from nirite.models.campaign_analysis import CampaignAnalysis
from nirite.models.company import CompanyProspect
from nirite.models.prospect import Prospect
from nirite.qualification.models import (
    CandidateVerdict,
    CriterionStatus,
    CriterionVerdict,
    QualificationOutput,
    VerdictStatus,
)
from nirite.qualification.policy import aggregate_verdict, compute_preference_score
from nirite.qualification.questions import plan_questions
from nirite.qualification.structured import evaluate_structured
from nirite.retrieval.models import Candidate, RetrievalOutput


def _prospect_hash(prospect_data: dict) -> str:
    """Stable SHA256 of prospect identifying fields — never full PII."""
    import hashlib
    import json

    key_fields = {
        k: prospect_data.get(k)
        for k in ("full_name", "company_name", "email", "linkedin_url")
        if prospect_data.get(k)
    }
    return hashlib.sha256(json.dumps(key_fields, sort_keys=True).encode()).hexdigest()[
        :16
    ]


def _prospect_label(prospect_data: dict, prospect_type: str) -> str:
    """Display label for CLI output."""
    if prospect_type == "company":
        return prospect_data.get("company_name", "Unknown Company")
    return prospect_data.get("full_name", "Unknown Person")


def _prospect_model(
    prospect_data: dict,
    prospect_type: str,
) -> Prospect | CompanyProspect:
    """Reconstruct a Pydantic prospect model from a data dict."""
    if prospect_type == "company":
        return CompanyProspect.model_validate(prospect_data)
    return Prospect.model_validate(prospect_data)


def _campaign_hash(definition: CampaignDefinition) -> str:
    """Stable hash of campaign definition for audit trail."""
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(definition.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()[:16]


def _build_judge_subject(prospect_data: dict) -> dict:
    """Build minimal subject data for the judge — only whitelisted fields."""
    whitelisted = (
        "full_name",
        "job_title",
        "company_name",
        "industry",
        "company_size",
        "country",
        "state",
        "city",
        "region",
        "description",
        "linkedin_url",
    )
    return {
        k: v for k, v in prospect_data.items() if k in whitelisted and v is not None
    }


def qualify(
    candidates: list[Candidate],
    definition: CampaignDefinition,
    analysis: CampaignAnalysis,
    judge_client: JudgeClient,
) -> QualificationOutput:
    """Run Layer 3 qualification on candidates against a campaign definition.

    Returns a QualificationOutput. Raises JudgeError if the judge fails
    (fail-closed — no partial output).
    """
    if definition.status.value == "needs_clarification":
        raise ValueError(
            "cannot qualify against a campaign definition with open clarifications"
        )

    criteria = definition.spec.criteria
    # Case-insensitive lookup: analyser emits IDs like C1/C2, parser assigns
    # c1/c2. Match case-insensitively so criteria link back to their analysis.
    analysis_by_id = {c.id.lower(): c for c in analysis.explicit_criteria}

    # Split criteria by evaluation mode
    structured = [c for c in criteria if c.evaluation_mode.value == "structured"]
    semantic = [
        c for c in criteria if c.evaluation_mode.value in ("semantic", "hybrid")
    ]

    # Plan judge questions for semantic/hybrid criteria (from AnalysisCriterion)
    analysis_semantic = [
        analysis_by_id[c.id.lower()] for c in semantic if c.id.lower() in analysis_by_id
    ]
    questions = plan_questions(analysis_semantic)

    verdicts: list[CandidateVerdict] = []

    for candidate in candidates:
        prospect_data = candidate.prospect_data
        prospect_type = candidate.prospect_type

        # Phase 1: structured checks (zero LLM) — short-circuit on failure
        structured_verdicts: list[CriterionVerdict] = []
        short_circuit_status: VerdictStatus | None = None
        short_circuit_reasons: list[str] = []

        for crit in structured:
            prospect_model = _prospect_model(prospect_data, prospect_type)
            verdict = evaluate_structured(prospect_model, crit)
            structured_verdicts.append(verdict)

            if (
                crit.kind.value == "exclusion"
                and verdict.status == CriterionStatus.FAILED
            ):
                short_circuit_status = VerdictStatus.NOT_QUALIFIED
                short_circuit_reasons = [f"exclusion matched: {crit.id}"]
                break
            if (
                crit.kind.value == "requirement"
                and verdict.status == CriterionStatus.FAILED
            ):
                short_circuit_status = VerdictStatus.NOT_QUALIFIED
                short_circuit_reasons = [f"requirement not met: {crit.id}"]
                break

        if short_circuit_status is not None:
            # No LLM call — structured failure is decisive
            criterion_verdicts = structured_verdicts
            # Add remaining criteria as unknown (not evaluated)
            remaining_ids = {c.id for c in criteria} - {
                cv.criterion_id for cv in structured_verdicts
            }
            for rid in remaining_ids:
                crit = next(c for c in criteria if c.id == rid)
                criterion_verdicts.append(
                    CriterionVerdict(
                        criterion_id=crit.id,
                        kind=crit.kind.value,
                        mode_used=crit.evaluation_mode.value,
                        status=CriterionStatus.UNKNOWN,
                        score=0.0,
                        evidence="not evaluated due to short-circuit",
                        judge_answer_ids=[],
                    )
                )
            status = short_circuit_status
            reasons = short_circuit_reasons
            preference_score = 0.0
        else:
            # Phase 2: batched judge call for semantic criteria
            criterion_verdicts = list(structured_verdicts)

            if questions:
                subject = _build_judge_subject(prospect_data)
                answers = judge_client.judge(questions, subject)

                questions_by_criterion: dict[str, list[JudgeQuestion]] = {}
                for q in questions:
                    # Case-insensitive keys: plan_questions uses analysis
                    # criterion IDs (may be uppercase), definition criteria
                    # use lowercase IDs from assign_stable_ids.
                    questions_by_criterion.setdefault(
                        q.criterion_id.lower(), []
                    ).append(q)

                for crit in semantic:
                    crit_questions = questions_by_criterion.get(crit.id.lower(), [])
                    crit_question_ids = {q.id.lower() for q in crit_questions}
                    crit_answers = [
                        a for a in answers if a.question_id.lower() in crit_question_ids
                    ]
                    score = score_verdict(crit_questions, crit_answers)
                    status = (
                        CriterionStatus.PASSED
                        if score >= 0.5
                        else CriterionStatus.FAILED
                    )
                    criterion_verdicts.append(
                        CriterionVerdict(
                            criterion_id=crit.id,
                            kind=crit.kind.value,
                            mode_used=crit.evaluation_mode.value,
                            status=status,
                            score=score,
                            evidence="judge evaluation",
                            judge_answer_ids=[a.question_id for a in crit_answers],
                        )
                    )

            # Add any criteria not covered (shouldn't happen, but be safe)
            covered_ids = {cv.criterion_id for cv in criterion_verdicts}
            for crit in criteria:
                if crit.id not in covered_ids:
                    criterion_verdicts.append(
                        CriterionVerdict(
                            criterion_id=crit.id,
                            kind=crit.kind.value,
                            mode_used=crit.evaluation_mode.value,
                            status=CriterionStatus.UNKNOWN,
                            score=0.0,
                            evidence="not evaluated",
                            judge_answer_ids=[],
                        )
                    )

            # Aggregate via policy
            status, reasons = aggregate_verdict(criterion_verdicts)
            preference_score = compute_preference_score(criterion_verdicts)

        verdicts.append(
            CandidateVerdict(
                rank=candidate.rank,
                prospect_hash=_prospect_hash(prospect_data),
                prospect_label=_prospect_label(prospect_data, prospect_type),
                status=status,
                criterion_verdicts=criterion_verdicts,
                preference_score=preference_score,
                reasons=reasons,
            )
        )

    # Order: qualified > bordered > not_qualified, tie-break on preference
    # score then RRF rank
    status_order = {
        VerdictStatus.QUALIFIED: 0,
        VerdictStatus.BORDERED: 1,
        VerdictStatus.NOT_QUALIFIED: 2,
    }
    verdicts.sort(
        key=lambda v: (
            status_order[v.status],
            -v.preference_score,
            v.rank,
        )
    )

    # Assign final ranks
    for idx, v in enumerate(verdicts, start=1):
        v.rank = idx

    # Counts
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v.status.value] = counts.get(v.status.value, 0) + 1

    return QualificationOutput(
        campaign_hash=_campaign_hash(definition),
        judge_model=judge_client.provider.model,  # type: ignore[attr-defined]
        prompt_version="1",
        verdicts=verdicts,
        counts=counts,
    )


def qualify_from_retrieval_output(
    retrieval_output: RetrievalOutput,
    definition: CampaignDefinition,
    analysis: CampaignAnalysis,
    judge_client: JudgeClient,
) -> QualificationOutput:
    """Convenience: qualify from a Layer 2 RetrievalOutput."""
    candidates = list(retrieval_output.candidates)
    return qualify(candidates, definition, analysis, judge_client)
