import pytest
from pydantic import ValidationError

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

@pytest.fixture
def valid_campaign_data():
    return {
        "original_prompt": "Find mid-sized logistics technology companies.",
        "spec": {
            "target_type": "company",
            "objective": "Find potential customers for AI automation.",
            "target_description": (
                "Mid-sized logistics technology companies that could "
                "benefit from AI automation."
            ),
            "criteria": [
                {
                    "id": "crit_1",
                    "description": "Company operates in logistics technology.",
                    "kind": "requirement",
                    "evaluation_mode": "semantic",
                    "predicate": None,
                    "weight": None,
                    "evidence_hints": [
                        "Company develops logistics or supply-chain software."
                    ],
                }
            ],
        },
        "query_plan": {
            "queries": [
                {
                    "id": "q1",
                    "query": "logistics technology companies",
                    "facet": "industry",
                    "rationale": "Find companies in the target industry.",
                }
            ]
        },
        "clarifications": [],
        "schema_version": 1,
        "version": 1,
    }

def test_valid_structured_criterion():
    criterion = Criterion(
        id="city",
        description="Company is located in Sydney.",
        kind=CriterionKind.REQUIREMENT,
        evaluation_mode=EvaluationMode.STRUCTURED,
        predicate=FieldPredicate(
            field="city",
            operator=PredicateOperator.EQ,
            value="Sydney",
        ),
    )

    assert criterion.predicate.field == PredicateField.CITY

def test_structured_criterion_requires_predicate():
    with pytest.raises(ValidationError, match="require a predicate"):
        Criterion(
            id="employee_count",
            description="Company has 10 to 100 employees.",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
        )

def test_semantic_criterion_does_not_accept_predicate():
    predicate = FieldPredicate(
        field=PredicateField.COUNTRY,
        operator=PredicateOperator.EQ,
        value="Australia",
    )

    with pytest.raises(ValidationError, match="cannot have a predicate"):
        Criterion(
            id="b2b_saas",
            description="Serves B2B SaaS customers.",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.SEMANTIC,
            predicate=predicate,
        )

def test_only_preferences_can_have_weights():
    predicate = FieldPredicate(
        field=PredicateField.COUNTRY,
        operator=PredicateOperator.EQ,
        value="Australia",
    )

    with pytest.raises(ValidationError, match="Only preferences"):
        Criterion(
            id="country",
            description="Located in Australia.",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=predicate,
            weight=0.8,
        )

def test_between_requires_upper_value():
    with pytest.raises(ValidationError, match="BETWEEN requires upper_value"):
        FieldPredicate(
            field=PredicateField.JOB_TITLE,
            operator=PredicateOperator.BETWEEN,
            value="a",
        )

def test_exists_does_not_accept_values():
    with pytest.raises(ValidationError, match="EXISTS must not contain"):
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

    with pytest.raises(ValidationError, match="unique"):
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

    with pytest.raises(ValidationError, match="Duplicate search queries"):
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

def test_campaign_without_clarifications_is_ready(valid_campaign_data):
    valid_campaign_data["status"] = CampaignStatus.NEEDS_CLARIFICATION
    valid_campaign_data["clarifications"] = []

    campaign = CampaignDefinition.model_validate(valid_campaign_data)

    assert campaign.status == CampaignStatus.READY

def test_status_needs_clarification_when_questions_exist(valid_campaign_data):
    valid_campaign_data["clarifications"] = [
        {
            "question": "What employee range defines mid-sized?",
            "reason": "Company size is ambiguous.",
            "related_criterion_ids": ["crit_1"],
        }
    ]

    campaign = CampaignDefinition.model_validate(valid_campaign_data)

    assert campaign.status == CampaignStatus.NEEDS_CLARIFICATION


def test_status_ready_without_clarifications(valid_campaign_data):
    valid_campaign_data["clarifications"] = []

    campaign = CampaignDefinition.model_validate(valid_campaign_data)

    assert campaign.status == CampaignStatus.READY


def test_status_overrides_llm_provided_status(valid_campaign_data):
    valid_campaign_data["status"] = CampaignStatus.READY
    valid_campaign_data["clarifications"] = [
        {
            "question": "What employee range defines mid-sized?",
            "reason": "Company size is ambiguous.",
            "related_criterion_ids": ["crit_1"],
        }
    ]

    campaign = CampaignDefinition.model_validate(valid_campaign_data)

    assert campaign.status == CampaignStatus.NEEDS_CLARIFICATION


def test_predicate_fields_exist_on_prospect():
    from nirite.models.prospect import Prospect

    assert {f.value for f in PredicateField} <= set(Prospect.model_fields)