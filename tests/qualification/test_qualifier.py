"""Tests for qualifier orchestrator (TASK-13)."""

from __future__ import annotations

from nirite.judge.client import JudgeClient, JudgeError
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
from nirite.models.campaign_analysis import (
    AnalysisCriterion,
    CampaignAmbiguity,
    CampaignAnalysis,
)
from nirite.qualification.models import VerdictStatus
from nirite.qualification.qualifier import qualify
from nirite.retrieval.models import Candidate, ProspectEntry
from tests.support.fakes import FakeLLMProvider


def _make_judge_client(responses: list[str]) -> JudgeClient:
    provider = FakeLLMProvider(responses=responses)
    return JudgeClient(provider)


def _make_criterion(
    *,
    id: str = "c1",
    kind: CriterionKind = CriterionKind.REQUIREMENT,
    mode: EvaluationMode = EvaluationMode.STRUCTURED,
    field: PredicateField | None = PredicateField.COUNTRY,
    operator: PredicateOperator | None = PredicateOperator.EQ,
    value: str | None = "Australia",
) -> Criterion:
    predicate = None
    if mode == EvaluationMode.STRUCTURED and field is not None:
        predicate = FieldPredicate(
            field=field,
            operator=operator,
            value=value,
        )
    return Criterion(
        id=id,
        description=f"Test {id}",
        kind=kind,
        evaluation_mode=mode,
        predicate=predicate,
    )


def _make_analysis_criterion(
    *,
    id: str = "c1",
    kind: CriterionKind = CriterionKind.REQUIREMENT,
) -> AnalysisCriterion:
    return AnalysisCriterion(
        id=id,
        description=f"Test {id}",
        kind=kind,
        source_phrase="test phrase",
    )


def _make_definition(
    *,
    criteria=None,
    status=CampaignStatus.READY,
    clarifications=None,
) -> CampaignDefinition:
    if criteria is None:
        criteria = [_make_criterion()]
    spec = CampaignSpec(
        target_type=TargetType.COMPANY,
        objective="Test objective",
        target_description="Test description",
        criteria=criteria,
    )
    query_plan = QueryPlan(
        queries=[
            SearchQuery(
                id="q1",
                query="test query",
                facet=SearchFacet.INDUSTRY,
                rationale="test rationale",
            )
        ]
    )
    return CampaignDefinition.model_construct(
        original_prompt="test prompt",
        spec=spec,
        query_plan=query_plan,
        clarifications=clarifications or [],
        status=status,
        schema_version=1,
        version=1,
    )


def _make_analysis(
    *,
    criteria=None,
) -> CampaignAnalysis:
    if criteria is None:
        criteria = [_make_analysis_criterion()]
    return CampaignAnalysis(
        target_type=TargetType.COMPANY,
        objective="Test objective",
        target_description="Test description",
        explicit_criteria=criteria,
        ambiguities=[],
    )


def _make_candidate(
    *,
    rank: int = 1,
    prospect_data: dict | None = None,
    prospect_type: str = "individual",
) -> Candidate:
    if prospect_data is None:
        prospect_data = {
            "full_name": "Jane Doe",
            "job_title": "Engineer",
            "company_name": "Acme",
            "country": "Australia",
            "source_file": "test.csv",
            "source_row": 1,
        }
    ProspectEntry(
        prospect_data=prospect_data,
        prospect_type=prospect_type,
        score=0.9,
        rank=rank,
    )
    return Candidate(
        prospect_data=prospect_data,
        prospect_type=prospect_type,
        final_score=0.9,
        rank=rank,
        queries_found=["q1"],
        match_reasons=["matched"],
    )


def test_qualify_all_requirements_passed() -> None:
    """All requirements pass → QUALIFIED, no judge call needed."""
    prospect_data = {
        "full_name": "Jane Doe",
        "job_title": "Engineer",
        "company_name": "Acme",
        "country": "Australia",
        "source_file": "test.csv",
        "source_row": 1,
    }
    candidate = _make_candidate(prospect_data=prospect_data)

    # Criterion: country=Australia (structured) → passes
    crit = _make_criterion(
        id="c1",
        kind=CriterionKind.REQUIREMENT,
        mode=EvaluationMode.STRUCTURED,
        field=PredicateField.COUNTRY,
        operator=PredicateOperator.EQ,
        value="Australia",
    )
    definition = _make_definition(criteria=[crit])
    analysis = _make_analysis(criteria=[_make_analysis_criterion(id="c1")])

    client = _make_judge_client(responses=[])
    output = qualify([candidate], definition, analysis, client)

    assert len(output.verdicts) == 1
    assert output.verdicts[0].status == VerdictStatus.QUALIFIED
    assert client.provider.call_count == 0  # no LLM call for structured pass


def test_qualify_requirement_failed() -> None:
    """Requirement fails → NOT_QUALIFIED, no judge call."""
    prospect_data = {
        "full_name": "Jane Doe",
        "job_title": "Engineer",
        "company_name": "Acme",
        "country": "Germany",
        "source_file": "test.csv",
        "source_row": 1,
    }
    candidate = _make_candidate(prospect_data=prospect_data)

    crit = _make_criterion(
        id="c1",
        kind=CriterionKind.REQUIREMENT,
        mode=EvaluationMode.STRUCTURED,
        field=PredicateField.COUNTRY,
        operator=PredicateOperator.EQ,
        value="Australia",
    )
    definition = _make_definition(criteria=[crit])
    analysis = _make_analysis(criteria=[_make_analysis_criterion(id="c1")])

    client = _make_judge_client(responses=[])
    output = qualify([candidate], definition, analysis, client)

    assert output.verdicts[0].status == VerdictStatus.NOT_QUALIFIED
    assert client.provider.call_count == 0


def test_qualify_exclusion_matched() -> None:
    """Exclusion matches → NOT_QUALIFIED, no judge call."""
    prospect_data = {
        "full_name": "Jane Doe",
        "job_title": "Recruiter",
        "company_name": "Staffing Co",
        "country": "Australia",
        "source_file": "test.csv",
        "source_row": 1,
    }
    candidate = _make_candidate(prospect_data=prospect_data)

    crit = _make_criterion(
        id="c1",
        kind=CriterionKind.EXCLUSION,
        mode=EvaluationMode.STRUCTURED,
        field=PredicateField.JOB_TITLE,
        operator=PredicateOperator.CONTAINS,
        value="recruit",
    )
    definition = _make_definition(criteria=[crit])
    analysis = _make_analysis(criteria=[_make_analysis_criterion(id="c1")])

    client = _make_judge_client(responses=[])
    output = qualify([candidate], definition, analysis, client)

    assert output.verdicts[0].status == VerdictStatus.NOT_QUALIFIED
    assert client.provider.call_count == 0


def test_qualify_semantic_criterion() -> None:
    """Semantic criterion → judge called, verdict based on score."""
    prospect_data = {
        "full_name": "Jane Doe",
        "job_title": "Engineering Manager",
        "company_name": "Acme",
        "country": "Australia",
        "source_file": "test.csv",
        "source_row": 1,
    }
    candidate = _make_candidate(prospect_data=prospect_data)

    # Structured: country=Australia → passes
    structured = _make_criterion(
        id="c1",
        kind=CriterionKind.REQUIREMENT,
        mode=EvaluationMode.STRUCTURED,
        field=PredicateField.COUNTRY,
        operator=PredicateOperator.EQ,
        value="Australia",
    )
    # Semantic: "uses AI" → judge decides
    semantic = _make_criterion(
        id="c2",
        kind=CriterionKind.PREFERENCE,
        mode=EvaluationMode.SEMANTIC,
    )
    definition = _make_definition(criteria=[structured, semantic])
    analysis = _make_analysis(
        criteria=[
            _make_analysis_criterion(id="c1", kind=CriterionKind.REQUIREMENT),
            _make_analysis_criterion(id="c2", kind=CriterionKind.PREFERENCE),
        ]
    )

    # Judge answers YES for the semantic question
    client = _make_judge_client(
        responses=[
            '{"answers": [{"question_id": "c2.q1", "answer": "yes", "evidence_field": "job_title", "evidence_quote": "Engineering Manager"}]}'
        ]
    )
    output = qualify([candidate], definition, analysis, client)

    assert output.verdicts[0].status == VerdictStatus.QUALIFIED
    assert client.provider.call_count == 1


def test_qualify_judge_error_propagates() -> None:
    """JudgeError propagates — no partial output."""
    prospect_data = {
        "full_name": "Jane Doe",
        "job_title": "Engineer",
        "company_name": "Acme",
        "country": "Australia",
        "source_file": "test.csv",
        "source_row": 1,
    }
    candidate = _make_candidate(prospect_data=prospect_data)

    semantic = _make_criterion(
        id="c1", kind=CriterionKind.PREFERENCE, mode=EvaluationMode.SEMANTIC
    )
    definition = _make_definition(criteria=[semantic])
    analysis = _make_analysis(
        criteria=[_make_analysis_criterion(id="c1", kind=CriterionKind.PREFERENCE)]
    )

    # Judge returns malformed JSON twice → JudgeError
    client = _make_judge_client(responses=["bad json", "also bad"])
    try:
        qualify([candidate], definition, analysis, client)
    except JudgeError:
        pass


def test_qualify_needs_clarification_rejected() -> None:
    """Definition with open clarifications is rejected up front."""
    candidate = _make_candidate()
    definition = _make_definition(
        clarifications=[
            CampaignAmbiguity(
                id="a1",
                topic="Company size",
                original_term="mid-sized",
                question="How do you define mid-sized?",
                affected_criterion_ids=["c1"],
            )
        ],
        status=CampaignStatus.NEEDS_CLARIFICATION,
    )
    analysis = _make_analysis()
    client = _make_judge_client(responses=[])

    try:
        qualify([candidate], definition, analysis, client)
    except ValueError as exc:
        assert "clarifications" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_qualify_empty_candidates() -> None:
    """Empty candidate list → empty output."""
    definition = _make_definition()
    analysis = _make_analysis()
    client = _make_judge_client(responses=[])
    output = qualify([], definition, analysis, client)

    assert output.verdicts == []
    assert output.counts == {}


def test_qualify_ordering() -> None:
    """Qualified > bordered > not_qualified, tie-break on preference score."""
    # Candidate 1: not qualified
    c1_data = {
        "full_name": "Failed Candidate",
        "job_title": "Engineer",
        "company_name": "Acme",
        "country": "Germany",
        "source_file": "test.csv",
        "source_row": 1,
    }
    c1 = _make_candidate(rank=1, prospect_data=c1_data)

    # Candidate 2: qualified
    c2_data = {
        "full_name": "Passed Candidate",
        "job_title": "Engineer",
        "company_name": "Acme",
        "country": "Australia",
        "source_file": "test.csv",
        "source_row": 2,
    }
    c2 = _make_candidate(rank=2, prospect_data=c2_data)

    crit = _make_criterion(
        id="c1",
        kind=CriterionKind.REQUIREMENT,
        mode=EvaluationMode.STRUCTURED,
        field=PredicateField.COUNTRY,
        operator=PredicateOperator.EQ,
        value="Australia",
    )
    definition = _make_definition(criteria=[crit])
    analysis = _make_analysis(criteria=[_make_analysis_criterion(id="c1")])

    client = _make_judge_client(responses=[])
    output = qualify([c1, c2], definition, analysis, client)

    assert output.verdicts[0].status == VerdictStatus.QUALIFIED
    assert output.verdicts[0].prospect_label == "Passed Candidate"
    assert output.verdicts[1].status == VerdictStatus.NOT_QUALIFIED
    assert output.verdicts[1].prospect_label == "Failed Candidate"


def test_qualify_multiple_candidates_judge_calls() -> None:
    """One judge call per candidate with semantic criteria."""
    c1_data = {
        "full_name": "Candidate 1",
        "job_title": "Engineer",
        "company_name": "Acme",
        "country": "Australia",
        "source_file": "test.csv",
        "source_row": 1,
    }
    c2_data = {
        "full_name": "Candidate 2",
        "job_title": "Engineer",
        "company_name": "Acme",
        "country": "Australia",
        "source_file": "test.csv",
        "source_row": 2,
    }
    c1 = _make_candidate(rank=1, prospect_data=c1_data)
    c2 = _make_candidate(rank=2, prospect_data=c2_data)

    semantic = _make_criterion(
        id="c1", kind=CriterionKind.PREFERENCE, mode=EvaluationMode.SEMANTIC
    )
    definition = _make_definition(criteria=[semantic])
    analysis = _make_analysis(
        criteria=[_make_analysis_criterion(id="c1", kind=CriterionKind.PREFERENCE)]
    )

    # 2 candidates → 2 judge calls
    client = _make_judge_client(
        responses=[
            '{"answers": [{"question_id": "c1.q1", "answer": "yes", "evidence_field": null, "evidence_quote": null}]}',
            '{"answers": [{"question_id": "c1.q1", "answer": "no", "evidence_field": null, "evidence_quote": null}]}',
        ]
    )
    output = qualify([c1, c2], definition, analysis, client)

    assert client.provider.call_count == 2
    assert (
        output.verdicts[0].status == VerdictStatus.BORDERED
    )  # preference only → bordered
    assert output.verdicts[1].status == VerdictStatus.BORDERED


def test_qualify_counts() -> None:
    """Counts match verdicts."""
    c1_data = {
        "full_name": "Passed",
        "job_title": "Engineer",
        "company_name": "Acme",
        "country": "Australia",
        "source_file": "test.csv",
        "source_row": 1,
    }
    c2_data = {
        "full_name": "Failed",
        "job_title": "Engineer",
        "company_name": "Acme",
        "country": "Germany",
        "source_file": "test.csv",
        "source_row": 2,
    }
    c1 = _make_candidate(rank=1, prospect_data=c1_data)
    c2 = _make_candidate(rank=2, prospect_data=c2_data)

    crit = _make_criterion(
        id="c1",
        kind=CriterionKind.REQUIREMENT,
        mode=EvaluationMode.STRUCTURED,
        field=PredicateField.COUNTRY,
        operator=PredicateOperator.EQ,
        value="Australia",
    )
    definition = _make_definition(criteria=[crit])
    analysis = _make_analysis(criteria=[_make_analysis_criterion(id="c1")])

    client = _make_judge_client(responses=[])
    output = qualify([c1, c2], definition, analysis, client)

    assert output.counts == {"qualified": 1, "not_qualified": 1}
    assert output.qualified_count == 1
    assert output.not_qualified_count == 1
    assert output.bordered_count == 0
