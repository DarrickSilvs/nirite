"""Cross-artifact consistency checks between CampaignAnalysis and CampaignDefinition.

Detects criteria the parser dropped, invented, or kind-flipped; flags criteria
with no query facet coverage; detects contradictory requirement/exclusion
pairs; and checks target_type alignment. All checks are deterministic —
casefold + token-set Jaccard ≥ 0.8 matching, no embeddings, no LLM.
"""

from __future__ import annotations

from nirite.eval.models import EvalFinding, EvalSeverity, FindingCode
from nirite.models.campaign import CampaignDefinition, CriterionKind
from nirite.models.campaign_analysis import CampaignAnalysis


def _token_set(text: str) -> set[str]:
    return {t for t in text.casefold().split() if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _match_score(analysis_crit, definition_crit) -> float:
    """Token-set Jaccard between description/source_phrase and definition description."""
    analysis_text = analysis_crit.source_phrase or analysis_crit.description or ""
    def_text = definition_crit.description or ""
    return _jaccard(_token_set(analysis_text), _token_set(def_text))


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


def check_criteria_coverage(
    analysis: CampaignAnalysis, definition: CampaignDefinition
) -> list[EvalFinding]:
    """Match analysis criteria to definition criteria; flag dropped/invented/extra."""
    def_criteria = {c.id: c for c in definition.spec.criteria}
    findings: list[EvalFinding] = []

    # Build a fuzzy match from analysis criteria to definition criteria by description similarity.
    matched_def_ids: set[str] = set()
    for a_crit in analysis.explicit_criteria:
        best_def_id: str | None = None
        best_score = 0.0
        for d_id, d_crit in def_criteria.items():
            if d_id in matched_def_ids:
                continue
            score = _match_score(a_crit, d_crit)
            if score > best_score:
                best_score = score
                best_def_id = d_id

        if best_def_id is not None and best_score >= 0.8:
            matched_def_ids.add(best_def_id)
            d_crit = def_criteria[best_def_id]
            # Kind flip check
            if a_crit.kind != d_crit.kind:
                findings.append(
                    _finding(
                        check_id="check_criteria_coverage",
                        code=FindingCode.CRITERION_KIND_FLIPPED,
                        severity=EvalSeverity.ERROR,
                        message=(
                            f"criterion '{a_crit.id}' kind changed from "
                            f"{a_crit.kind.value} to {d_crit.kind.value}"
                        ),
                        path=f"spec.criteria[{best_def_id}].kind",
                        evidence=f"{a_crit.id}->{best_def_id}",
                    )
                )
        else:
            # Dropped: no definition criterion matched well enough
            findings.append(
                _finding(
                    check_id="check_criteria_coverage",
                    code=FindingCode.CRITERION_DROPPED,
                    severity=EvalSeverity.ERROR,
                    message=(
                        f"analysis criterion '{a_crit.id}' ('{a_crit.description[:50]}') "
                        f"has no matching definition criterion"
                    ),
                    path="spec.criteria",
                    evidence=a_crit.id,
                )
            )

    # Invented: definition criteria not matched to any analysis criterion
    for d_id, d_crit in def_criteria.items():
        if d_id not in matched_def_ids:
            findings.append(
                _finding(
                    check_id="check_criteria_coverage",
                    code=FindingCode.CRITERION_INVENTED,
                    severity=EvalSeverity.ERROR,
                    message=(
                        f"definition criterion '{d_id}' ('{d_crit.description[:50]}') "
                        f"has no matching analysis criterion"
                    ),
                    path=f"spec.criteria[{d_id}]",
                    evidence=d_id,
                )
            )

    return findings


def check_facet_coverage(
    definition: CampaignDefinition,
) -> list[EvalFinding]:
    """Flag criteria with no query facet coverage."""
    covered_facets: set[str] = {q.facet.value for q in definition.query_plan.queries}
    findings: list[EvalFinding] = []
    for criterion in definition.spec.criteria:
        # Heuristic: infer expected facet from criterion predicate field or description keywords.
        expected_facet = _infer_facet(criterion)
        if expected_facet and expected_facet not in covered_facets:
            findings.append(
                _finding(
                    check_id="check_facet_coverage",
                    code=FindingCode.CRITERION_FACET_UNCOVERED,
                    severity=EvalSeverity.WARN,
                    message=(
                        f"criterion '{criterion.id}' needs facet '{expected_facet.value}' "
                        f"but no query covers it"
                    ),
                    path=f"spec.criteria[{criterion.id}]",
                    evidence=criterion.id,
                )
            )
    return findings


def _infer_facet(criterion) -> object:
    """Infer expected SearchFacet from criterion predicate field or description."""
    from nirite.models.campaign import PredicateField, SearchFacet

    if criterion.predicate is not None:
        mapping = {
            PredicateField.INDUSTRY: SearchFacet.INDUSTRY,
            PredicateField.COMPANY_SIZE: SearchFacet.COMPANY_SIZE,
            PredicateField.COUNTRY: SearchFacet.GEOGRAPHY,
            PredicateField.STATE: SearchFacet.GEOGRAPHY,
            PredicateField.CITY: SearchFacet.GEOGRAPHY,
            PredicateField.JOB_TITLE: SearchFacet.ROLE,
            PredicateField.DESCRIPTION: SearchFacet.SERVICE,
        }
        return mapping.get(criterion.predicate.field)
    return None


def check_contradictory_predicates(
    definition: CampaignDefinition,
) -> list[EvalFinding]:
    """Flag contradictory requirement/exclusion pairs (same field, opposing values)."""
    requirements = [
        c
        for c in definition.spec.criteria
        if c.kind == CriterionKind.REQUIREMENT and c.predicate is not None
    ]
    exclusions = [
        c
        for c in definition.spec.criteria
        if c.kind == CriterionKind.EXCLUSION and c.predicate is not None
    ]
    findings: list[EvalFinding] = []
    for req in requirements:
        for exc in exclusions:
            if (
                req.predicate.field == exc.predicate.field
                and req.predicate.operator == exc.predicate.operator
                and req.predicate.value == exc.predicate.value
            ):
                findings.append(
                    _finding(
                        check_id="check_contradictory_predicates",
                        code=FindingCode.CONTRADICTORY_PREDICATES,
                        severity=EvalSeverity.ERROR,
                        message=(
                            f"requirement '{req.id}' and exclusion '{exc.id}' "
                            f"have identical predicates — mutually contradictory"
                        ),
                        path=f"spec.criteria[{req.id}].predicate",
                        evidence=f"{req.id} vs {exc.id}",
                    )
                )
    return findings


def check_target_type_alignment(
    analysis: CampaignAnalysis, definition: CampaignDefinition
) -> list[EvalFinding]:
    """Flag target_type mismatch between analysis and definition."""
    findings: list[EvalFinding] = []
    if analysis.target_type != definition.spec.target_type:
        findings.append(
            _finding(
                check_id="check_target_type_alignment",
                code=FindingCode.TARGET_TYPE_MISMATCH,
                severity=EvalSeverity.ERROR,
                message=(
                    f"analysis target_type '{analysis.target_type.value}' differs "
                    f"from definition '{definition.spec.target_type.value}'"
                ),
                path="spec.target_type",
                evidence=analysis.target_type.value,
            )
        )
    return findings


def check_consistency(
    analysis: CampaignAnalysis, definition: CampaignDefinition
) -> list[EvalFinding]:
    """Run all cross-artifact consistency checks. Never raises."""
    findings: list[EvalFinding] = []
    findings.extend(check_criteria_coverage(analysis, definition))
    findings.extend(check_facet_coverage(definition))
    findings.extend(check_contradictory_predicates(definition))
    findings.extend(check_target_type_alignment(analysis, definition))
    return findings
