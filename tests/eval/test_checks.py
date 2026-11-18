"""Tests for deterministic structural checks (TASK-04).

Uses ``model_construct`` to bypass Pydantic's own validators so we can test
the check functions independently — they are meant to catch issues that
Pydantic either doesn't check or that surface when parsing raw LLM JSON.
"""

from __future__ import annotations

from nirite.eval.checks import (
    check_clarification_references,
    check_definition,
    check_duplicate_query_text,
    check_non_empty_query_text,
    check_query_count_range,
    check_schema_valid,
    check_structured_requires_predicate,
    check_unique_criterion_ids,
    check_unique_query_ids,
    check_weight_only_on_preferences,
)
from nirite.eval.models import EvalSeverity, FindingCode
from nirite.models.campaign import (
    CampaignDefinition,
    CampaignSpec,
    CampaignStatus,
    Criterion,
    CriterionKind,
    EvaluationMode,
    FieldPredicate,
    PredicateField,
    PredicateOperator,
    QueryPlan,
    TargetType,
)
from tests.support.builders import (
    build_campaign_ambiguity,
    build_criterion,
    build_definition,
    build_search_query,
)


def _make_definition(
    *,
    criteria=None,
    queries=None,
    clarifications=None,
    status=CampaignStatus.READY,
) -> CampaignDefinition:
    """Build a CampaignDefinition, bypassing Pydantic validation via model_construct."""
    if criteria is None:
        criteria = [build_criterion(id="c1", description="Must be based in Australia")]
    if queries is None:
        queries = [build_search_query(id="q1", query="SaaS companies Australia")]
    if clarifications is None:
        clarifications = []
    spec = CampaignSpec.model_construct(
        target_type=TargetType.COMPANY,
        objective="Find suitable companies",
        target_description="Australian SaaS companies",
        criteria=criteria,
    )
    query_plan = QueryPlan.model_construct(queries=queries)
    return CampaignDefinition.model_construct(
        original_prompt="Find Australian SaaS companies",
        spec=spec,
        query_plan=query_plan,
        clarifications=clarifications,
        status=status,
        schema_version=1,
        version=1,
    )


def test_clean_definition_zero_findings() -> None:
    definition = _make_definition()
    findings = check_definition(definition)
    assert findings == []


def test_duplicate_criterion_ids() -> None:
    definition = _make_definition(
        criteria=[
            build_criterion(id="c1", description="A"),
            build_criterion(id="c1", description="B"),
        ]
    )
    findings = check_unique_criterion_ids(definition)
    codes = [f.code for f in findings]
    assert FindingCode.DUPLICATE_CRITERION_ID in codes
    assert all(f.severity == EvalSeverity.ERROR for f in findings)


def test_duplicate_query_ids() -> None:
    definition = _make_definition(
        queries=[
            build_search_query(id="q1", query="query one"),
            build_search_query(id="q1", query="query two"),
        ]
    )
    findings = check_unique_query_ids(definition)
    codes = [f.code for f in findings]
    assert FindingCode.DUPLICATE_QUERY_ID in codes


def test_query_count_zero() -> None:
    definition = _make_definition(queries=[])
    findings = check_query_count_range(definition)
    codes = [f.code for f in findings]
    assert FindingCode.QUERY_COUNT_OUT_OF_RANGE in codes


def test_query_count_too_many() -> None:
    definition = _make_definition(
        queries=[build_search_query(id=f"q{i}", query=f"query {i}") for i in range(8)]
    )
    findings = check_query_count_range(definition)
    codes = [f.code for f in findings]
    assert FindingCode.QUERY_COUNT_OUT_OF_RANGE in codes


def test_empty_query_text() -> None:
    definition = _make_definition(queries=[build_search_query(id="q1", query="   ")])
    findings = check_non_empty_query_text(definition)
    codes = [f.code for f in findings]
    assert FindingCode.EMPTY_QUERY_TEXT in codes


def test_duplicate_query_text() -> None:
    definition = _make_definition(
        queries=[
            build_search_query(id="q1", query="SaaS companies Australia"),
            build_search_query(id="q2", query="saas companies australia"),
        ]
    )
    findings = check_duplicate_query_text(definition)
    codes = [f.code for f in findings]
    assert FindingCode.DUPLICATE_QUERY_TEXT in codes


def test_weight_on_non_preference() -> None:
    definition = _make_definition(
        criteria=[
            Criterion.model_construct(
                id="c1",
                description="Must be based in Australia",
                kind=CriterionKind.REQUIREMENT,
                evaluation_mode=EvaluationMode.STRUCTURED,
                predicate=FieldPredicate(
                    field=PredicateField.COUNTRY,
                    operator=PredicateOperator.EQ,
                    value="Australia",
                ),
                weight=0.5,
                evidence_hints=[],
            )
        ]
    )
    findings = check_weight_only_on_preferences(definition)
    codes = [f.code for f in findings]
    assert FindingCode.WEIGHT_ON_NON_PREFERENCE in codes


def test_structured_without_predicate() -> None:
    definition = _make_definition(
        criteria=[
            Criterion.model_construct(
                id="c1",
                description="Must be based in Australia",
                kind=CriterionKind.REQUIREMENT,
                evaluation_mode=EvaluationMode.STRUCTURED,
                predicate=None,
                weight=None,
                evidence_hints=[],
            )
        ]
    )
    findings = check_structured_requires_predicate(definition)
    codes = [f.code for f in findings]
    assert FindingCode.STRUCTURED_WITHOUT_PREDICATE in codes


def test_semantic_with_predicate() -> None:
    definition = _make_definition(
        criteria=[
            Criterion.model_construct(
                id="c1",
                description="Must be based in Australia",
                kind=CriterionKind.PREFERENCE,
                evaluation_mode=EvaluationMode.SEMANTIC,
                predicate=FieldPredicate(
                    field=PredicateField.COUNTRY,
                    operator=PredicateOperator.EQ,
                    value="Australia",
                ),
                weight=0.5,
                evidence_hints=[],
            )
        ]
    )
    findings = check_definition(definition)
    codes = [f.code for f in findings]
    assert FindingCode.SEMANTIC_WITH_PREDICATE in codes


def test_clarification_references_unknown() -> None:
    definition = _make_definition(
        criteria=[build_criterion(id="c1", description="A")],
        clarifications=[
            build_campaign_ambiguity(id="a1", affected_criterion_ids=["c99"])
        ],
    )
    findings = check_clarification_references(definition)
    codes = [f.code for f in findings]
    assert FindingCode.CLARIFICATION_REFERENCES_UNKNOWN in codes


def test_needs_clarification_incoherent() -> None:
    definition = _make_definition(
        criteria=[build_criterion(id="c1", description="A")],
        clarifications=[
            build_campaign_ambiguity(id="a1", affected_criterion_ids=["c1"])
        ],
        status=CampaignStatus.READY,
    )
    findings = check_definition(definition)
    codes = [f.code for f in findings]
    assert FindingCode.NEEDS_CLARIFICATION_INCOHERENT in codes


def test_all_findings_reported() -> None:
    definition = _make_definition(
        criteria=[
            build_criterion(id="c1", description="A"),
            build_criterion(id="c1", description="B"),
            Criterion.model_construct(
                id="c2",
                description="Weighted requirement",
                kind=CriterionKind.REQUIREMENT,
                evaluation_mode=EvaluationMode.STRUCTURED,
                predicate=FieldPredicate(
                    field=PredicateField.COUNTRY,
                    operator=PredicateOperator.EQ,
                    value="Australia",
                ),
                weight=0.5,
                evidence_hints=[],
            ),
        ],
        queries=[
            build_search_query(id="q1", query="   "),
            build_search_query(id="q1", query="dup"),
            build_search_query(id="q2", query="dup"),
        ],
    )
    findings = check_definition(definition)
    codes = {f.code for f in findings}
    assert FindingCode.DUPLICATE_CRITERION_ID in codes
    assert FindingCode.WEIGHT_ON_NON_PREFERENCE in codes
    assert FindingCode.EMPTY_QUERY_TEXT in codes
    assert FindingCode.DUPLICATE_QUERY_ID in codes
    assert FindingCode.DUPLICATE_QUERY_TEXT in codes


def test_check_definition_never_raises() -> None:
    definition = _make_definition(
        criteria=[build_criterion(id="c1", description="A")],
        clarifications=[
            build_campaign_ambiguity(id="a1", affected_criterion_ids=["missing"])
        ],
    )
    findings = check_definition(definition)
    assert isinstance(findings, list)
    assert len(findings) >= 1


def test_findings_have_codes_and_messages() -> None:
    definition = _make_definition(
        criteria=[
            build_criterion(id="c1", description="A"),
            build_criterion(id="c1", description="B"),
        ]
    )
    findings = check_unique_criterion_ids(definition)
    dup_findings = [f for f in findings if f.code == FindingCode.DUPLICATE_CRITERION_ID]
    assert len(dup_findings) == 1
    f = dup_findings[0]
    assert f.check_id == "check_unique_criterion_ids"
    assert f.severity == EvalSeverity.ERROR
    assert "c1" in f.message
    assert f.evidence == "c1"


def test_schema_valid_passes_for_clean_definition() -> None:
    definition = build_definition()
    findings = check_schema_valid(definition)
    assert findings == []


def test_schema_valid_reports_invalid_json() -> None:
    """check_schema_valid converts ValidationError into findings instead of raising."""
    # Build a definition with empty criteria via model_construct (bypasses min_length=1)
    spec = CampaignSpec.model_construct(
        target_type=TargetType.COMPANY,
        objective="find",
        target_description="companies",
        criteria=[],
    )
    query_plan = QueryPlan.model_construct(queries=[])
    definition = CampaignDefinition.model_construct(
        original_prompt="test",
        spec=spec,
        query_plan=query_plan,
        clarifications=[],
        status=CampaignStatus.READY,
        schema_version=1,
        version=1,
    )
    findings = check_schema_valid(definition)
    assert any(f.code == FindingCode.SCHEMA_INVALID for f in findings)
    assert all(
        f.severity == EvalSeverity.ERROR
        for f in findings
        if f.code == FindingCode.SCHEMA_INVALID
    )
