import pytest
from pydantic import ValidationError

from nirite.campaign.models import (
    CampaignDefinition,
    CampaignSpec,
    CampaignStatus,
    Criterion,
    CriterionKind,
    EvaluationMode,
    FieldPredicate,
    PredicateOperator,
    QueryPlan,
    SearchFacet,
    SearchQuery,
    TargetType,
)

def test_valid_structured_criterion():
    criterion = Criterion(
        id="employee_count",
        description="Company has 10 to 100 employees.",
        kind=CriterionKind.REQUIREMENT,
        evaluation_mode=EvaluationMode.STRUCTURED,
        predicate=FieldPredicate(
            field="employee_count",
            operator=PredicateOperator.BETWEEN,
            value=10,
            upper_value=100,
        ),
    )

    assert criterion.predicate.field == "employee_count"
    assert criterion.predicate.value == 10

def test_structured_criterion_requires_predicate():
    with pytest.raises(ValidationError):
        Criterion(
            id="employee_count",
            description="Company has 10 to 100 employees.",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
        )

def test_semantic_criterion_does_not_accept_predicate():
    with pytest.raises(ValidationError):
        Criterion(
            id="b2b_saas",
            description="Serves B2B SaaS customers.",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.SEMANTIC,
            predicate=FieldPredicate(
                field="industry",
                operator=PredicateOperator.EQ,
                value="SaaS",
            ),
        )

def test_only_preferences_can_have_weights():
    with pytest.raises(ValidationError):
        Criterion(
            id="employee_count",
            description="Has at least 10 employees.",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=FieldPredicate(
                field="employee_count",
                operator=PredicateOperator.GTE,
                value=10,
            ),
            weight=0.8,
        )


def test_between_requires_upper_value():
    with pytest.raises(ValidationError):
        FieldPredicate(
            field="employee_count",
            operator=PredicateOperator.BETWEEN,
            value=10,
        )

def test_exists_does_not_accept_values():
    with pytest.raises(ValidationError):
        FieldPredicate(
            field="company_website",
            operator=PredicateOperator.EXISTS,
            value=True,
        )

def test_campaign_spec_rejects_duplicate_criterion_ids():
    criterion = Criterion(
        id="b2b_saas",
        description="Serves B2B SaaS customers.",
        kind=CriterionKind.REQUIREMENT,
        evaluation_mode=EvaluationMode.SEMANTIC,
    )

    with pytest.raises(ValidationError):
        CampaignSpec(
            target_type=TargetType.COMPANY,
            objective="Find suitable agencies.",
            target_description="B2B marketing agencies.",
            criteria=[criterion, criterion],
        )

def test_query_plan_rejects_duplicate_queries():
    query = SearchQuery(
        id="q1",
        query="Australian B2B agencies",
        facet=SearchFacet.INDUSTRY,
        rationale="Direct industry match.",
    )

    duplicate = SearchQuery(
        id="q2",
        query="Australian B2B agencies",
        facet=SearchFacet.SERVICE,
        rationale="Alternative search angle.",
    )

    with pytest.raises(ValidationError):
        QueryPlan(queries=[query, duplicate])

def test_query_plan_rejects_more_than_seven_queries():
    queries = [
        SearchQuery(
            id=f"q{i}",
            query=f"Unique search query {i}",
            facet=SearchFacet.OTHER,
            rationale="Test query.",
        )
        for i in range(8)
    ]

    with pytest.raises(ValidationError):
        QueryPlan(queries=queries)

def test_campaign_needing_clarification_requires_question():
    with pytest.raises(ValidationError):
        CampaignDefinition(
            original_prompt="Find marketing agencies.",
            spec=CampaignSpec(
                target_type=TargetType.COMPANY,
                objective="Find agencies.",
                target_description="Marketing agencies.",
                criteria=[
                    Criterion(
                        id="b2b",
                        description="Serves B2B customers.",
                        kind=CriterionKind.REQUIREMENT,
                        evaluation_mode=EvaluationMode.SEMANTIC,
                    )
                ],
            ),
            query_plan=QueryPlan(
                queries=[
                    SearchQuery(
                        id="q1",
                        query="B2B marketing agencies",
                        facet=SearchFacet.INDUSTRY,
                        rationale="Direct match.",
                    )
                ]
            ),
            status=CampaignStatus.NEEDS_CLARIFICATION,
        )
