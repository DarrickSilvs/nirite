"""Tests for definition quality judge (TASK-15)."""

from __future__ import annotations

from nirite.eval.models import FindingCode
from nirite.eval.quality import (
    QUALITY_RUBRIC_VERSION,
    STRICT_THRESHOLD,
    run_quality_eval,
)
from nirite.judge.client import JudgeClient
from nirite.models.campaign import (
    CampaignDefinition,
    CampaignSpec,
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
from tests.support.fakes import FakeLLMProvider


def _make_judge_client(responses: list[str]) -> JudgeClient:
    return JudgeClient(FakeLLMProvider(responses=responses))


def _make_definition_proper() -> CampaignDefinition:
    return CampaignDefinition(
        original_prompt="Find Australian SaaS companies",
        spec=CampaignSpec(
            target_type=TargetType.COMPANY,
            objective="Find Australian SaaS companies",
            target_description="Australian SaaS companies",
            criteria=[
                Criterion(
                    id="c1",
                    description="Australian SaaS companies",
                    kind=CriterionKind.REQUIREMENT,
                    evaluation_mode=EvaluationMode.STRUCTURED,
                    predicate=FieldPredicate(
                        field=PredicateField.COUNTRY,
                        operator=PredicateOperator.EQ,
                        value="Australia",
                    ),
                )
            ],
        ),
        query_plan=QueryPlan(
            queries=[
                SearchQuery(
                    id="q1",
                    query="SaaS companies Australia",
                    facet=SearchFacet.INDUSTRY,
                    rationale="Find SaaS companies in Australia",
                )
            ]
        ),
    )


def _make_analysis() -> CampaignAnalysis:
    return CampaignAnalysis(
        target_type=TargetType.COMPANY,
        objective="Find Australian SaaS companies",
        target_description="Australian SaaS companies",
        explicit_criteria=[
            AnalysisCriterion(
                id="c1",
                description="Australian SaaS companies",
                kind=CriterionKind.REQUIREMENT,
                source_phrase="Australian SaaS companies",
            )
        ],
        ambiguities=[],
    )


def test_quality_all_yes_passes() -> None:
    definition = _make_definition_proper()
    _make_analysis()
    client = _make_judge_client(
        responses=[
            (
                '{"answers": ['
                '{"question_id": "q1", "answer": "yes", "evidence_field": "objective", "evidence_quote": "Find Australian SaaS companies"},'
                '{"question_id": "q2", "answer": "yes", "evidence_field": "target_description", "evidence_quote": "Australian SaaS companies"},'
                '{"question_id": "q3", "answer": "yes", "evidence_field": "criteria", "evidence_quote": "none invented"},'
                '{"question_id": "q4", "answer": "yes", "evidence_field": "query_plan", "evidence_quote": "specific queries"}'
                "]}"
            )
        ]
    )
    report = run_quality_eval("Find Australian SaaS companies", definition, client)
    assert report.passed is True
    assert report.error_count == 0


def test_quality_one_no_fails_strict() -> None:
    definition = _make_definition_proper()
    _make_analysis()
    client = _make_judge_client(
        responses=[
            (
                '{"answers": ['
                '{"question_id": "q1", "answer": "yes", "evidence_field": null, "evidence_quote": null},'
                '{"question_id": "q2", "answer": "no", "evidence_field": null, "evidence_quote": null},'
                '{"question_id": "q3", "answer": "yes", "evidence_field": null, "evidence_quote": null},'
                '{"question_id": "q4", "answer": "yes", "evidence_field": null, "evidence_quote": null}'
                "]}"
            )
        ]
    )
    report = run_quality_eval("Find Australian SaaS companies", definition, client)
    assert report.passed is False
    assert report.error_count == 1
    assert any(f.code == FindingCode.QUALITY_RUBRIC_FAIL for f in report.findings)


def test_quality_unknown_fails_strict() -> None:
    definition = _make_definition_proper()
    _make_analysis()
    client = _make_judge_client(
        responses=[
            (
                '{"answers": ['
                '{"question_id": "q1", "answer": "yes", "evidence_field": null, "evidence_quote": null},'
                '{"question_id": "q2", "answer": "unknown", "evidence_field": null, "evidence_quote": null},'
                '{"question_id": "q3", "answer": "yes", "evidence_field": null, "evidence_quote": null},'
                '{"question_id": "q4", "answer": "yes", "evidence_field": null, "evidence_quote": null}'
                "]}"
            )
        ]
    )
    report = run_quality_eval("Find Australian SaaS companies", definition, client)
    assert report.passed is False
    assert report.error_count == 1


def test_quality_judge_unavailable_fail_closed() -> None:
    """Judge unavailable → ERROR finding in strict mode, never a warning."""
    definition = _make_definition_proper()
    _make_analysis()
    client = _make_judge_client(responses=["bad json", "also bad"])
    report = run_quality_eval("Find Australian SaaS companies", definition, client)
    assert report.passed is False
    assert report.error_count == 1
    assert any(f.code == FindingCode.QUALITY_RUBRIC_FAIL for f in report.findings)


def test_strict_threshold_constant() -> None:
    assert STRICT_THRESHOLD == 1.0


def test_quality_rubric_version_constant() -> None:
    assert QUALITY_RUBRIC_VERSION == "1"
