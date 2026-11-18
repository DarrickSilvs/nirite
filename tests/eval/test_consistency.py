"""Tests for cross-artifact consistency checks (TASK-05)."""

from __future__ import annotations

from nirite.eval.consistency import check_consistency
from nirite.eval.models import FindingCode
from nirite.models.campaign import (
    CriterionKind,
    EvaluationMode,
    PredicateField,
    PredicateOperator,
    SearchFacet,
    TargetType,
)
from tests.support.builders import (
    build_analysis,
    build_analysis_criterion,
    build_criterion,
    build_definition,
    build_search_query,
)


def test_clean_analysis_definition_zero_findings() -> None:
    analysis = build_analysis(
        criteria=[
            build_analysis_criterion(
                id="c1",
                description="Australian companies",
                kind=CriterionKind.REQUIREMENT,
                source_phrase="Australian companies",
            )
        ]
    )
    definition = build_definition(
        criteria=[
            build_criterion(
                id="c1",
                description="Australian companies",
                kind=CriterionKind.REQUIREMENT,
                evaluation_mode=EvaluationMode.STRUCTURED,
            )
        ],
        queries=[
            build_search_query(
                id="q1",
                query="Australian companies",
                facet=SearchFacet.GEOGRAPHY,
            )
        ],
    )
    findings = check_consistency(analysis, definition)
    assert findings == []


def test_criterion_dropped() -> None:
    analysis = build_analysis(
        criteria=[
            build_analysis_criterion(
                id="c1",
                description="Australian companies",
                kind=CriterionKind.REQUIREMENT,
            ),
            build_analysis_criterion(
                id="c2", description="SaaS industry", kind=CriterionKind.REQUIREMENT
            ),
        ]
    )
    definition = build_definition(
        criteria=[
            build_criterion(
                id="c1",
                description="Australian companies",
                kind=CriterionKind.REQUIREMENT,
                evaluation_mode=EvaluationMode.STRUCTURED,
            )
        ]
    )
    findings = check_consistency(analysis, definition)
    codes = [f.code for f in findings]
    assert FindingCode.CRITERION_DROPPED in codes


def test_criterion_invented() -> None:
    analysis = build_analysis(
        criteria=[
            build_analysis_criterion(
                id="c1",
                description="Australian companies",
                kind=CriterionKind.REQUIREMENT,
            )
        ]
    )
    definition = build_definition(
        criteria=[
            build_criterion(
                id="c1",
                description="Australian companies",
                kind=CriterionKind.REQUIREMENT,
                evaluation_mode=EvaluationMode.STRUCTURED,
            ),
            build_criterion(
                id="c2",
                description="SaaS industry",
                kind=CriterionKind.PREFERENCE,
                evaluation_mode=EvaluationMode.SEMANTIC,
                predicate_field=None,
                predicate_operator=None,
                predicate_value=None,
            ),
        ]
    )
    findings = check_consistency(analysis, definition)
    codes = [f.code for f in findings]
    assert FindingCode.CRITERION_INVENTED in codes


def test_criterion_kind_flipped() -> None:
    analysis = build_analysis(
        criteria=[
            build_analysis_criterion(
                id="c1",
                description="Australian companies",
                kind=CriterionKind.REQUIREMENT,
            )
        ]
    )
    definition = build_definition(
        criteria=[
            build_criterion(
                id="c1",
                description="Australian companies",
                kind=CriterionKind.PREFERENCE,
                evaluation_mode=EvaluationMode.SEMANTIC,
                predicate_field=None,
                predicate_operator=None,
                predicate_value=None,
            )
        ]
    )
    findings = check_consistency(analysis, definition)
    codes = [f.code for f in findings]
    assert FindingCode.CRITERION_KIND_FLIPPED in codes


def test_contradictory_predicates() -> None:
    definition = build_definition(
        criteria=[
            build_criterion(
                id="c1",
                description="Australia only",
                kind=CriterionKind.REQUIREMENT,
                evaluation_mode=EvaluationMode.STRUCTURED,
                predicate_field=PredicateField.COUNTRY,
                predicate_operator=PredicateOperator.EQ,
                predicate_value="Australia",
            ),
            build_criterion(
                id="c2",
                description="Not Australia",
                kind=CriterionKind.EXCLUSION,
                evaluation_mode=EvaluationMode.STRUCTURED,
                predicate_field=PredicateField.COUNTRY,
                predicate_operator=PredicateOperator.EQ,
                predicate_value="Australia",
            ),
        ]
    )
    analysis = build_analysis()
    findings = check_consistency(analysis, definition)
    codes = [f.code for f in findings]
    assert FindingCode.CONTRADICTORY_PREDICATES in codes


def test_target_type_mismatch() -> None:
    analysis = build_analysis(target_type=TargetType.COMPANY)
    definition = build_definition(target_type=TargetType.PERSON)
    findings = check_consistency(analysis, definition)
    codes = [f.code for f in findings]
    assert FindingCode.TARGET_TYPE_MISMATCH in codes


def test_facet_uncovered() -> None:
    analysis = build_analysis()
    definition = build_definition(
        criteria=[
            build_criterion(
                id="c1",
                description="SaaS industry",
                kind=CriterionKind.REQUIREMENT,
                evaluation_mode=EvaluationMode.STRUCTURED,
                predicate_field=PredicateField.INDUSTRY,
                predicate_operator=PredicateOperator.EQ,
                predicate_value="SaaS",
            )
        ],
        queries=[
            build_search_query(
                id="q1",
                query="Australian companies",
                facet=SearchFacet.GEOGRAPHY,
            )
        ],
    )
    findings = check_consistency(analysis, definition)
    codes = [f.code for f in findings]
    assert FindingCode.CRITERION_FACET_UNCOVERED in codes


def test_case_insensitive_id_matching() -> None:
    """Analysis ID C1 matches definition ID c1 (case-insensitive)."""
    analysis = build_analysis(
        criteria=[
            build_analysis_criterion(
                id="C1",
                description="Australian companies",
                kind=CriterionKind.REQUIREMENT,
                source_phrase="Australian companies",
            )
        ]
    )
    definition = build_definition(
        criteria=[
            build_criterion(
                id="c1",
                description="Australian companies",
                kind=CriterionKind.REQUIREMENT,
                evaluation_mode=EvaluationMode.STRUCTURED,
            )
        ],
        queries=[
            build_search_query(
                id="q1",
                query="Australian companies",
                facet=SearchFacet.GEOGRAPHY,
            )
        ],
    )
    findings = check_consistency(analysis, definition)
    assert findings == []


def test_dropped_first_criterion_no_false_kind_flip() -> None:
    """Parser drops first criterion and renumbers — no false kind flip.

    Analysis: C1=requirement(exec roles), C2=exclusion(recruitment agencies).
    Parser keeps only C2, renumbers to c1. With pure ID matching, C1 would
    match c1 → false kind flip. With Jaccard+ID bonus, C1 vs c1 has zero
    description overlap → not matched; C2 vs c1 matches by description.
    """
    analysis = build_analysis(
        criteria=[
            build_analysis_criterion(
                id="C1",
                description="executive or director level roles",
                kind=CriterionKind.REQUIREMENT,
                source_phrase="executive or director level roles",
            ),
            build_analysis_criterion(
                id="C2",
                description="recruitment agencies",
                kind=CriterionKind.EXCLUSION,
                source_phrase="recruitment agencies",
            ),
        ]
    )
    # Parser dropped C1, kept C2, renumbered to c1
    definition = build_definition(
        criteria=[
            build_criterion(
                id="c1",
                description="recruitment agencies",
                kind=CriterionKind.EXCLUSION,
                evaluation_mode=EvaluationMode.STRUCTURED,
            )
        ],
        queries=[
            build_search_query(
                id="q1",
                query="recruitment agencies",
                facet=SearchFacet.SERVICE,
            )
        ],
    )
    findings = check_consistency(analysis, definition)
    codes = [f.code for f in findings]
    # C1 is dropped (no description match), C2 matched to c1 (same kind, no flip)
    assert FindingCode.CRITERION_DROPPED in codes
    assert FindingCode.CRITERION_KIND_FLIPPED not in codes
    assert FindingCode.CRITERION_INVENTED not in codes


def test_all_findings_reported() -> None:
    analysis = build_analysis(
        criteria=[
            build_analysis_criterion(
                id="c1", description="Dropped criterion", kind=CriterionKind.REQUIREMENT
            ),
            build_analysis_criterion(
                id="c2",
                description="Flipped criterion",
                kind=CriterionKind.REQUIREMENT,
                source_phrase="Flipped criterion",
            ),
        ]
    )
    definition = build_definition(
        criteria=[
            build_criterion(
                id="c2",
                description="Flipped criterion",
                kind=CriterionKind.PREFERENCE,
                evaluation_mode=EvaluationMode.SEMANTIC,
                predicate_field=None,
                predicate_operator=None,
                predicate_value=None,
            ),
            build_criterion(
                id="c3",
                description="Invented criterion",
                kind=CriterionKind.PREFERENCE,
                evaluation_mode=EvaluationMode.SEMANTIC,
                predicate_field=None,
                predicate_operator=None,
                predicate_value=None,
            ),
        ]
    )
    findings = check_consistency(analysis, definition)
    codes = {f.code for f in findings}
    assert FindingCode.CRITERION_DROPPED in codes
    assert FindingCode.CRITERION_KIND_FLIPPED in codes
    assert FindingCode.CRITERION_INVENTED in codes
