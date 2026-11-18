"""Structured criterion evaluator for Layer 3 qualification.

Reuses Tier 1 ``evaluate_predicate``, ``get_field_value``, ``_expand_geo_predicate``,
and ``_prospect_passes`` from ``retrieval/tier1_filter.py`` — does not copy or
move them. Produces tri-state verdicts: passed / failed / unknown.

Zero LLM, zero mutation of prospect inputs.
"""

from __future__ import annotations

from nirite.models.campaign import Criterion, CriterionKind
from nirite.models.company import CompanyProspect
from nirite.models.prospect import Prospect
from nirite.qualification.models import CriterionStatus, CriterionVerdict
from nirite.retrieval.tier1_filter import (
    _expand_geo_predicate,
    _prospect_passes,
    get_field_value,
)


def _field_is_absent(
    prospect: Prospect | CompanyProspect,
    predicate,
) -> bool:
    """Return True if the predicate field (and all geo-expanded fields) are absent."""
    checks = _expand_geo_predicate(
        predicate.field.value,
        predicate.operator.value,
        predicate.value,
    )
    return all(get_field_value(prospect, field) is None for field, _, _ in checks)


def evaluate_structured(
    prospect: Prospect | CompanyProspect,
    criterion: Criterion,
) -> CriterionVerdict:
    """Evaluate a structured criterion against a prospect.

    Returns a ``CriterionVerdict`` with status:
    - PASSED if the field value satisfies the predicate
    - FAILED if the field value is present but contradicts the predicate
    - UNKNOWN if the field is absent or cannot be resolved

    Exclusion polarity is handled here: for exclusion criteria, a predicate
    match means FAILED (disqualifying).
    """
    predicate = criterion.predicate
    if predicate is None:
        return CriterionVerdict(
            criterion_id=criterion.id,
            kind=criterion.kind.value,
            mode_used="structured",
            status=CriterionStatus.UNKNOWN,
            score=0.0,
            evidence="no predicate",
            judge_answer_ids=[],
        )

    # Delegate to Tier 1's _prospect_passes which handles geo expansion,
    # alias resolution, and all operators consistently.
    passes = _prospect_passes(predicate, prospect)

    if predicate.operator.value == "exists":
        # EXISTS: field absent → evaluate_predicate returns False → FAILED
        # (not UNKNOWN, because EXISTS explicitly checks for presence)
        if passes:
            status = CriterionStatus.PASSED
            evidence = f"field '{predicate.field.value}' exists"
        else:
            if criterion.kind == CriterionKind.EXCLUSION:
                status = CriterionStatus.PASSED  # exclusion not matched
                evidence = f"exclusion '{predicate.field.value}' does not exist"
            else:
                status = CriterionStatus.FAILED
                evidence = f"field '{predicate.field.value}' does not exist"
    else:
        if _field_is_absent(prospect, predicate):
            status = CriterionStatus.UNKNOWN
            evidence = f"field '{predicate.field.value}' absent"
        elif passes:
            if criterion.kind == CriterionKind.EXCLUSION:
                status = CriterionStatus.FAILED  # exclusion matched = disqualified
                evidence = f"exclusion matched: {predicate.field.value}"
            else:
                status = CriterionStatus.PASSED
                evidence = f"{predicate.field.value} {predicate.operator.value} {predicate.value}"
        else:
            if criterion.kind == CriterionKind.EXCLUSION:
                status = CriterionStatus.PASSED  # exclusion not matched
                evidence = "exclusion not matched"
            else:
                status = CriterionStatus.FAILED
                evidence = f"{predicate.field.value} {predicate.operator.value} {predicate.value}"

    return CriterionVerdict(
        criterion_id=criterion.id,
        kind=criterion.kind.value,
        mode_used="structured",
        status=status,
        score=1.0 if status == CriterionStatus.PASSED else 0.0,
        evidence=evidence,
        judge_answer_ids=[],
    )
