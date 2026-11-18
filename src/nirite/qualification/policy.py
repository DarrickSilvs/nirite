"""Verdict policy for Layer 3 qualification.

Aggregation rules (fail-closed):

- **Requirement**: ALL must be PASSED for QUALIFIED. Any FAILED → NOT_QUALIFIED.
  Any UNKNOWN → BORDERED (can't confirm a hard requirement).
- **Exclusion**: any PASSED → NOT_QUALIFIED (disqualifying). UNKNOWN/FAILED
  exclusions don't disqualify.
- **Preference**: scored but never changes the verdict — only used for tie-breaking.
- Unknown overall (no failures but some unknowns) → BORDERED.
- Empty criteria → BORDERED (nothing to qualify against).
"""

from __future__ import annotations

from nirite.qualification.models import CriterionStatus, VerdictStatus


def aggregate_verdict(
    criterion_verdicts: list,
    preference_score: float = 0.0,
) -> tuple[VerdictStatus, list[str]]:
    """Aggregate per-criterion verdicts into an overall verdict and reasons.

    Returns ``(status, reasons)``.
    """
    if not criterion_verdicts:
        return VerdictStatus.BORDERED, ["no criteria to evaluate"]

    reasons: list[str] = []

    # Separate by kind
    requirements = [cv for cv in criterion_verdicts if cv.kind == "requirement"]
    exclusions = [cv for cv in criterion_verdicts if cv.kind == "exclusion"]
    preferences = [cv for cv in criterion_verdicts if cv.kind == "preference"]

    # Exclusion check: any PASSED exclusion disqualifies
    failed_exclusions = [cv for cv in exclusions if cv.status == CriterionStatus.PASSED]
    if failed_exclusions:
        ids = ", ".join(cv.criterion_id for cv in failed_exclusions)
        return (
            VerdictStatus.NOT_QUALIFIED,
            [f"exclusion(s) matched: {ids}"],
        )

    # Requirement checks
    failed_requirements = [
        cv for cv in requirements if cv.status == CriterionStatus.FAILED
    ]
    unknown_requirements = [
        cv for cv in requirements if cv.status == CriterionStatus.UNKNOWN
    ]

    if failed_requirements:
        ids = ", ".join(cv.criterion_id for cv in failed_requirements)
        reasons.append(f"requirement(s) not met: {ids}")
        return VerdictStatus.NOT_QUALIFIED, reasons

    if unknown_requirements:
        ids = ", ".join(cv.criterion_id for cv in unknown_requirements)
        reasons.append(f"requirement(s) unknown: {ids}")
        return VerdictStatus.BORDERED, reasons

    # All requirements passed, no exclusions matched
    if not requirements:
        reasons.append("no requirement criteria defined")
        return VerdictStatus.BORDERED, reasons

    # Preference note
    if preferences:
        reasons.append(f"{len(preferences)} preference(s) scored")

    return VerdictStatus.QUALIFIED, reasons


def compute_preference_score(
    preference_verdicts: list,
) -> float:
    """Compute aggregated preference score (0.0 to 1.0) for tie-breaking.

    Averaged across preference criterion scores. Returns 0.0 if no preferences.
    """
    scores = [cv.score for cv in preference_verdicts if cv.kind == "preference"]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)
