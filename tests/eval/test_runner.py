"""Tests for eval runner (TASK-06).

Uses ``model_construct`` for invalid criterion combinations that Pydantic
would reject at construction time — the runner must handle them as findings,
not exceptions.
"""

from __future__ import annotations

from nirite.eval.models import EvalMode, FindingCode
from nirite.eval.runner import EvalFailure, assert_passing, run_definition_evals
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
    SearchFacet,
    SearchQuery,
    TargetType,
)
from nirite.models.campaign_analysis import AnalysisCriterion, CampaignAnalysis
from tests.support.builders import build_analysis


def _make_clean_analysis() -> CampaignAnalysis:
    return CampaignAnalysis(
        target_type=TargetType.COMPANY,
        objective="Find Australian companies",
        target_description="Australian SaaS companies",
        explicit_criteria=[
            AnalysisCriterion(
                id="c1",
                description="Australian companies",
                kind=CriterionKind.REQUIREMENT,
                source_phrase="Australian companies",
            )
        ],
        ambiguities=[],
    )


def _make_clean_definition() -> CampaignDefinition:
    spec = CampaignSpec(
        target_type=TargetType.COMPANY,
        objective="Find Australian companies",
        target_description="Australian SaaS companies",
        criteria=[
            Criterion(
                id="c1",
                description="Australian companies",
                kind=CriterionKind.REQUIREMENT,
                evaluation_mode=EvaluationMode.STRUCTURED,
                predicate=FieldPredicate(
                    field=PredicateField.COUNTRY,
                    operator=PredicateOperator.EQ,
                    value="Australia",
                ),
            )
        ],
    )
    query_plan = QueryPlan(
        queries=[
            SearchQuery(
                id="q1",
                query="Australian companies",
                facet=SearchFacet.GEOGRAPHY,
                rationale="Find Australian companies",
            )
        ],
    )
    return CampaignDefinition(
        original_prompt="Find Australian companies",
        spec=spec,
        query_plan=query_plan,
    )


def _make_definition_with_weight_on_requirement() -> CampaignDefinition:
    spec = CampaignSpec.model_construct(
        target_type=TargetType.COMPANY,
        objective="Find Australian companies",
        target_description="Australian SaaS companies",
        criteria=[
            Criterion.model_construct(
                id="c1",
                description="Bad criterion",
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
        ],
    )
    query_plan = QueryPlan.model_construct(
        queries=[
            SearchQuery(
                id="q1",
                query="Australian companies",
                facet=SearchFacet.GEOGRAPHY,
                rationale="Find Australian companies",
            )
        ],
    )
    return CampaignDefinition.model_construct(
        original_prompt="Find Australian companies",
        spec=spec,
        query_plan=query_plan,
        clarifications=[],
        status=CampaignStatus.READY,
        schema_version=1,
        version=1,
    )


def test_clean_definition_passes() -> None:
    analysis = _make_clean_analysis()
    definition = _make_clean_definition()
    report = run_definition_evals(definition, analysis, mode=EvalMode.STRICT)
    assert report.passed is True
    assert report.error_count == 0


def test_single_error_fails() -> None:
    analysis = build_analysis()
    definition = _make_definition_with_weight_on_requirement()
    report = run_definition_evals(definition, analysis, mode=EvalMode.STRICT)
    assert report.passed is False
    assert report.error_count >= 1


def test_multiple_findings_all_reported() -> None:
    analysis = build_analysis()
    spec = CampaignSpec.model_construct(
        target_type=TargetType.COMPANY,
        objective="Find Australian companies",
        target_description="Australian SaaS companies",
        criteria=[
            Criterion.model_construct(
                id="c1",
                description="Bad 1",
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
            Criterion.model_construct(
                id="c1",
                description="Bad 2",
                kind=CriterionKind.REQUIREMENT,
                evaluation_mode=EvaluationMode.STRUCTURED,
                predicate=FieldPredicate(
                    field=PredicateField.COUNTRY,
                    operator=PredicateOperator.EQ,
                    value="Australia",
                ),
                weight=0.3,
                evidence_hints=[],
            ),
        ],
    )
    query_plan = QueryPlan.model_construct(
        queries=[
            SearchQuery(
                id="q1",
                query="Australian companies",
                facet=SearchFacet.GEOGRAPHY,
                rationale="Find Australian companies",
            )
        ],
    )
    definition = CampaignDefinition.model_construct(
        original_prompt="Find Australian companies",
        spec=spec,
        query_plan=query_plan,
        clarifications=[],
        status=CampaignStatus.READY,
        schema_version=1,
        version=1,
    )
    report = run_definition_evals(definition, analysis, mode=EvalMode.STRICT)
    assert report.passed is False
    codes = {f.code for f in report.findings}
    assert FindingCode.WEIGHT_ON_NON_PREFERENCE in codes
    assert FindingCode.DUPLICATE_CRITERION_ID in codes


def test_assert_passing_raises_on_failure() -> None:
    analysis = build_analysis()
    definition = _make_definition_with_weight_on_requirement()
    report = run_definition_evals(definition, analysis, mode=EvalMode.STRICT)
    try:
        assert_passing(report)
    except EvalFailure as exc:
        assert exc.report is report
        assert exc.report.error_count >= 1
    else:
        raise AssertionError("assert_passing should have raised EvalFailure")


def test_assert_passing_ok_on_clean() -> None:
    analysis = _make_clean_analysis()
    definition = _make_clean_definition()
    report = run_definition_evals(definition, analysis, mode=EvalMode.STRICT)
    assert_passing(report)  # should not raise


def test_runner_never_calls_llm() -> None:
    """The runner must not import or call any LLM provider."""
    import nirite.eval.runner as runner_module

    source = runner_module.__file__
    assert source is not None
    with open(source) as f:
        content = f.read()
    assert "litellm" not in content
    assert "completion" not in content
    assert "LLMProvider" not in content
    assert "generate_json" not in content
