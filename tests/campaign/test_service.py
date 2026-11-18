"""Tests for the campaign build service (TASK-14)."""

from __future__ import annotations

import pytest

from nirite.campaign.service import MAX_RE_RUNS, build_campaign_definition
from nirite.eval.models import EvalSeverity, FindingCode
from nirite.eval.runner import EvalFailure
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
from nirite.models.campaign_analysis import (
    AnalysisCriterion,
    CampaignAnalysis,
)


class FakeAnalyser:
    """Returns canned analyses in order."""

    def __init__(self, analyses: list[list[CampaignAnalysis]]) -> None:
        self._analyses = analyses
        self._call_count = 0

    def analyse(self, prompt: str) -> list[CampaignAnalysis]:
        result = self._analyses[self._call_count]
        self._call_count += 1
        return result


class FakeParser:
    """Returns canned definitions in order."""

    def __init__(self, definitions: list[CampaignDefinition]) -> None:
        self._definitions = definitions
        self._call_count = 0

    def parse(
        self, prompt: str, analyses: list[CampaignAnalysis]
    ) -> CampaignDefinition:
        result = self._definitions[self._call_count]
        self._call_count += 1
        return result


def _make_analysis(
    criteria_ids: list[str],
    descriptions: list[str],
    kinds: list[CriterionKind],
) -> CampaignAnalysis:
    return CampaignAnalysis(
        target_type=TargetType.COMPANY,
        objective="Find companies",
        target_description="Australian companies",
        explicit_criteria=[
            AnalysisCriterion(
                id=cid,
                description=desc,
                kind=kind,
                source_phrase=desc,
            )
            for cid, desc, kind in zip(criteria_ids, descriptions, kinds)
        ],
        ambiguities=[],
    )


def _make_definition(
    criteria_ids: list[str],
    descriptions: list[str],
    kinds: list[CriterionKind],
) -> CampaignDefinition:
    return CampaignDefinition(
        original_prompt="Find Australian companies",
        spec=CampaignSpec(
            target_type=TargetType.COMPANY,
            objective="Find companies",
            target_description="Australian companies",
            criteria=[
                Criterion(
                    id=cid,
                    description=desc,
                    kind=kind,
                    evaluation_mode=EvaluationMode.STRUCTURED,
                    predicate=FieldPredicate(
                        field=PredicateField.COUNTRY,
                        operator=PredicateOperator.EQ,
                        value="Australia",
                    ),
                )
                for cid, desc, kind in zip(criteria_ids, descriptions, kinds)
            ],
        ),
        query_plan=QueryPlan(
            queries=[
                SearchQuery(
                    id="q1",
                    query="Australian companies",
                    facet=SearchFacet.GEOGRAPHY,
                    rationale="Find companies in Australia",
                )
            ]
        ),
    )


def test_build_campaign_definition_happy_path() -> None:
    """Analyser + parser succeed, eval passes — returns (definition, report)."""
    analysis = _make_analysis(
        ["c1"], ["Australian companies"], [CriterionKind.REQUIREMENT]
    )
    definition = _make_definition(
        ["c1"], ["Australian companies"], [CriterionKind.REQUIREMENT]
    )
    analyser = FakeAnalyser([[analysis]])
    parser = FakeParser([definition])

    result_def, report = build_campaign_definition(
        "Find Australian companies", analyser=analyser, parser=parser
    )

    assert result_def is definition
    assert report.passed is True
    assert analyser._call_count == 1
    assert parser._call_count == 1


def test_build_campaign_definition_empty_analysis_raises() -> None:
    """Analyser returns zero analyses — EvalFailure with ANALYSIS_EMPTY code."""
    analyser = FakeAnalyser([[]])
    parser = FakeParser([])  # never reached

    with pytest.raises(EvalFailure) as exc_info:
        build_campaign_definition(
            "Find Australian companies", analyser=analyser, parser=parser
        )

    report = exc_info.value.report
    assert report.passed is False
    assert any(f.code == FindingCode.ANALYSIS_EMPTY for f in report.findings)
    assert any(f.severity == EvalSeverity.ERROR for f in report.findings)


def test_build_campaign_definition_repair_then_pass() -> None:
    """First eval fails (criterion_dropped), repair re-run passes."""
    # First pass: analysis has C1, C2; definition only has c1 → C2 dropped
    analysis1 = _make_analysis(
        ["C1", "C2"],
        ["Australian companies", "SaaS industry"],
        [CriterionKind.REQUIREMENT, CriterionKind.REQUIREMENT],
    )
    definition1 = _make_definition(
        ["c1"], ["Australian companies"], [CriterionKind.REQUIREMENT]
    )

    # Second pass (repair): analysis has C1, C2; definition has c1, c2 → all match
    analysis2 = _make_analysis(
        ["C1", "C2"],
        ["Australian companies", "SaaS industry"],
        [CriterionKind.REQUIREMENT, CriterionKind.REQUIREMENT],
    )
    definition2 = _make_definition(
        ["c1", "c2"],
        ["Australian companies", "SaaS industry"],
        [CriterionKind.REQUIREMENT, CriterionKind.REQUIREMENT],
    )

    analyser = FakeAnalyser([[analysis1], [analysis2]])
    parser = FakeParser([definition1, definition2])

    result_def, report = build_campaign_definition(
        "Find Australian companies", analyser=analyser, parser=parser
    )

    assert result_def is definition2
    assert report.passed is True
    assert analyser._call_count == 2
    assert parser._call_count == 2


def test_build_campaign_definition_repair_exhausted_raises() -> None:
    """Both eval attempts fail — EvalFailure raised with last report."""
    # Both passes: analysis has C1, C2; definition only has c1 → C2 dropped both times
    analysis = _make_analysis(
        ["C1", "C2"],
        ["Australian companies", "SaaS industry"],
        [CriterionKind.REQUIREMENT, CriterionKind.REQUIREMENT],
    )
    definition = _make_definition(
        ["c1"], ["Australian companies"], [CriterionKind.REQUIREMENT]
    )

    analyser = FakeAnalyser([[analysis], [analysis]])
    parser = FakeParser([definition, definition])

    with pytest.raises(EvalFailure) as exc_info:
        build_campaign_definition(
            "Find Australian companies", analyser=analyser, parser=parser
        )

    report = exc_info.value.report
    assert report.passed is False
    assert any(f.code == FindingCode.CRITERION_DROPPED for f in report.findings)
    assert analyser._call_count == MAX_RE_RUNS + 1  # 2 attempts
    assert parser._call_count == MAX_RE_RUNS + 1  # 2 attempts


def test_max_re_runs_bounds_attempts() -> None:
    """MAX_RE_RUNS = 1 means at most 2 total attempts (original + 1 repair)."""
    analysis = _make_analysis(
        ["C1", "C2"],
        ["Australian companies", "SaaS industry"],
        [CriterionKind.REQUIREMENT, CriterionKind.REQUIREMENT],
    )
    definition = _make_definition(
        ["c1"], ["Australian companies"], [CriterionKind.REQUIREMENT]
    )

    analyser = FakeAnalyser([[analysis], [analysis]])
    parser = FakeParser([definition, definition])

    with pytest.raises(EvalFailure):
        build_campaign_definition("Find companies", analyser=analyser, parser=parser)

    assert analyser._call_count == 2  # MAX_RE_RUNS + 1
    assert parser._call_count == 2  # MAX_RE_RUNS + 1
