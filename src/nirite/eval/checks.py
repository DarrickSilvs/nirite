"""Deterministic structural checks on ``CampaignDefinition``.

Each check is a pure function ``(definition) -> list[EvalFinding]`` that
never raises for bad input — it returns findings instead. Checks are
ordered cheap to expensive so the runner can short-circuit in strict mode.
"""

from __future__ import annotations

from pydantic import ValidationError

from nirite.eval.models import EvalFinding, EvalSeverity, FindingCode
from nirite.models.campaign import (
    CampaignDefinition,
    CriterionKind,
    EvaluationMode,
)


def _finding(
    check_id: str,
    code: FindingCode,
    severity: EvalSeverity,
    message: str,
    *,
    path: str | None = None,
    evidence: str | None = None,
) -> EvalFinding:
    return EvalFinding(
        check_id=check_id,
        code=code,
        severity=severity,
        message=message,
        path=path,
        evidence=evidence,
    )


def check_schema_valid(definition: CampaignDefinition) -> list[EvalFinding]:
    """Re-validate the definition against its Pydantic schema.

    Converts ``ValidationError`` into findings instead of raising.
    """
    try:
        CampaignDefinition.model_validate(definition.model_dump(mode="json"))
        return []
    except ValidationError as exc:
        findings: list[EvalFinding] = []
        for error in exc.errors():
            loc = ".".join(str(part) for part in error.get("loc", []))
            findings.append(
                _finding(
                    check_id="check_schema",
                    code=FindingCode.SCHEMA_INVALID,
                    severity=EvalSeverity.ERROR,
                    message=error.get("msg", "schema validation failed"),
                    path=loc or None,
                    evidence=str(error.get("input", ""))[:80]
                    if error.get("input") is not None
                    else None,
                )
            )
        return findings


def check_unique_criterion_ids(definition: CampaignDefinition) -> list[EvalFinding]:
    """Flag duplicate criterion IDs (Pydantic also enforces, but we report findings)."""
    seen: set[str] = set()
    findings: list[EvalFinding] = []
    for criterion in definition.spec.criteria:
        if criterion.id in seen:
            findings.append(
                _finding(
                    check_id="check_unique_criterion_ids",
                    code=FindingCode.DUPLICATE_CRITERION_ID,
                    severity=EvalSeverity.ERROR,
                    message=f"duplicate criterion id '{criterion.id}'",
                    path=f"spec.criteria[{criterion.id}]",
                    evidence=criterion.id,
                )
            )
        seen.add(criterion.id)
    return findings


def check_unique_query_ids(definition: CampaignDefinition) -> list[EvalFinding]:
    """Flag duplicate query IDs."""
    seen: set[str] = set()
    findings: list[EvalFinding] = []
    for query in definition.query_plan.queries:
        if query.id in seen:
            findings.append(
                _finding(
                    check_id="check_unique_query_ids",
                    code=FindingCode.DUPLICATE_QUERY_ID,
                    severity=EvalSeverity.ERROR,
                    message=f"duplicate query id '{query.id}'",
                    path=f"query_plan.queries[{query.id}]",
                    evidence=query.id,
                )
            )
        seen.add(query.id)
    return findings


def check_query_count_range(definition: CampaignDefinition) -> list[EvalFinding]:
    """Flag query plan with 0 or more than 7 queries."""
    count = len(definition.query_plan.queries)
    findings: list[EvalFinding] = []
    if count == 0:
        findings.append(
            _finding(
                check_id="check_query_count_range",
                code=FindingCode.QUERY_COUNT_OUT_OF_RANGE,
                severity=EvalSeverity.ERROR,
                message="query plan must contain at least 1 query",
                path="query_plan.queries",
                evidence=str(count),
            )
        )
    elif count > 7:
        findings.append(
            _finding(
                check_id="check_query_count_range",
                code=FindingCode.QUERY_COUNT_OUT_OF_RANGE,
                severity=EvalSeverity.ERROR,
                message=f"query plan has {count} queries, maximum is 7",
                path="query_plan.queries",
                evidence=str(count),
            )
        )
    return findings


def check_non_empty_query_text(definition: CampaignDefinition) -> list[EvalFinding]:
    """Flag queries with empty or whitespace-only text."""
    findings: list[EvalFinding] = []
    for query in definition.query_plan.queries:
        if not query.query or not query.query.strip():
            findings.append(
                _finding(
                    check_id="check_non_empty_query_text",
                    code=FindingCode.EMPTY_QUERY_TEXT,
                    severity=EvalSeverity.ERROR,
                    message=f"query '{query.id}' has empty text",
                    path=f"query_plan.queries[{query.id}].query",
                    evidence=query.id,
                )
            )
    return findings


def check_duplicate_query_text(definition: CampaignDefinition) -> list[EvalFinding]:
    """Flag queries with identical text (case-insensitive)."""
    seen: dict[str, str] = {}
    findings: list[EvalFinding] = []
    for query in definition.query_plan.queries:
        key = query.query.casefold().strip()
        if key in seen:
            findings.append(
                _finding(
                    check_id="check_duplicate_query_text",
                    code=FindingCode.DUPLICATE_QUERY_TEXT,
                    severity=EvalSeverity.WARN,
                    message=f"query '{query.id}' duplicates text of '{seen[key]}'",
                    path=f"query_plan.queries[{query.id}].query",
                    evidence=query.query[:60],
                )
            )
        else:
            seen[key] = query.id
    return findings


def check_weight_only_on_preferences(
    definition: CampaignDefinition,
) -> list[EvalFinding]:
    """Flag non-preference criteria that carry a weight."""
    findings: list[EvalFinding] = []
    for criterion in definition.spec.criteria:
        if criterion.kind != CriterionKind.PREFERENCE and criterion.weight is not None:
            findings.append(
                _finding(
                    check_id="check_weight_only_on_preferences",
                    code=FindingCode.WEIGHT_ON_NON_PREFERENCE,
                    severity=EvalSeverity.ERROR,
                    message=f"criterion '{criterion.id}' has weight but kind is {criterion.kind.value}",
                    path=f"spec.criteria[{criterion.id}].weight",
                    evidence=criterion.id,
                )
            )
    return findings


def check_structured_requires_predicate(
    definition: CampaignDefinition,
) -> list[EvalFinding]:
    """Flag structured criteria without a predicate."""
    findings: list[EvalFinding] = []
    for criterion in definition.spec.criteria:
        if (
            criterion.evaluation_mode == EvaluationMode.STRUCTURED
            and criterion.predicate is None
        ):
            findings.append(
                _finding(
                    check_id="check_structured_requires_predicate",
                    code=FindingCode.STRUCTURED_WITHOUT_PREDICATE,
                    severity=EvalSeverity.ERROR,
                    message=f"structured criterion '{criterion.id}' has no predicate",
                    path=f"spec.criteria[{criterion.id}].predicate",
                    evidence=criterion.id,
                )
            )
    return findings


def check_semantic_excludes_predicate(
    definition: CampaignDefinition,
) -> list[EvalFinding]:
    """Flag semantic criteria that incorrectly carry a predicate."""
    findings: list[EvalFinding] = []
    for criterion in definition.spec.criteria:
        if (
            criterion.evaluation_mode == EvaluationMode.SEMANTIC
            and criterion.predicate is not None
        ):
            findings.append(
                _finding(
                    check_id="check_semantic_excludes_predicate",
                    code=FindingCode.SEMANTIC_WITH_PREDICATE,
                    severity=EvalSeverity.ERROR,
                    message=f"semantic criterion '{criterion.id}' has a predicate",
                    path=f"spec.criteria[{criterion.id}].predicate",
                    evidence=criterion.id,
                )
            )
    return findings


def check_clarification_references(definition: CampaignDefinition) -> list[EvalFinding]:
    """Flag clarifications that reference unknown criterion IDs."""
    known = {c.id for c in definition.spec.criteria}
    findings: list[EvalFinding] = []
    for clarification in definition.clarifications:
        unknown = set(clarification.affected_criterion_ids) - known
        for ref_id in sorted(unknown):
            findings.append(
                _finding(
                    check_id="check_clarification_references",
                    code=FindingCode.CLARIFICATION_REFERENCES_UNKNOWN,
                    severity=EvalSeverity.ERROR,
                    message=f"clarification '{clarification.id}' references unknown criterion '{ref_id}'",
                    path=f"clarifications[{clarification.id}].related_criterion_ids",
                    evidence=ref_id,
                )
            )
    return findings


def check_needs_clarification_coherence(
    definition: CampaignDefinition,
) -> list[EvalFinding]:
    """Flag incoherence between clarifications and status."""
    has_clarifications = len(definition.clarifications) > 0
    findings: list[EvalFinding] = []

    if has_clarifications and definition.status.value == "ready":
        findings.append(
            _finding(
                check_id="check_needs_clarification_coherence",
                code=FindingCode.NEEDS_CLARIFICATION_INCOHERENT,
                severity=EvalSeverity.WARN,
                message="clarifications present but status is READY (should be NEEDS_CLARIFICATION)",
                path="status",
                evidence=str(len(definition.clarifications)),
            )
        )

    if not has_clarifications and definition.status.value == "needs_clarification":
        findings.append(
            _finding(
                check_id="check_needs_clarification_coherence",
                code=FindingCode.NEEDS_CLARIFICATION_INCOHERENT,
                severity=EvalSeverity.WARN,
                message="status is NEEDS_CLARIFICATION but no clarifications present",
                path="status",
                evidence=str(len(definition.clarifications)),
            )
        )

    return findings


def check_definition(definition: CampaignDefinition) -> list[EvalFinding]:
    """Run all structural checks and return aggregated findings.

    Checks run in order: schema → IDs → query count → text → weights →
    predicate pairing → clarifications → coherence. Never raises.
    """
    findings: list[EvalFinding] = []
    findings.extend(check_schema_valid(definition))
    findings.extend(check_unique_criterion_ids(definition))
    findings.extend(check_unique_query_ids(definition))
    findings.extend(check_query_count_range(definition))
    findings.extend(check_non_empty_query_text(definition))
    findings.extend(check_duplicate_query_text(definition))
    findings.extend(check_weight_only_on_preferences(definition))
    findings.extend(check_structured_requires_predicate(definition))
    findings.extend(check_semantic_excludes_predicate(definition))
    findings.extend(check_clarification_references(definition))
    findings.extend(check_needs_clarification_coherence(definition))
    return findings
