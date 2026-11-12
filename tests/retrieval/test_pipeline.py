"""Tests for retrieval pipeline."""

from unittest.mock import MagicMock

import pytest

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
from nirite.models.company import CompanyProspect
from nirite.models.prospect import Prospect

from nirite.retrieval.pipeline import run


def _prospect(full_name, company_name, city, country, source_row, extra_fields=None):
    return Prospect(
        full_name=full_name,
        first_name=full_name.split()[0],
        last_name=full_name.split()[-1],
        job_title="Engineer",
        company_name=company_name,
        company_domain=f"{company_name.lower().replace(' ', '')}.com",
        company_website=f"https://{company_name.lower().replace(' ', '')}.com",
        email=f"{full_name.split()[0].lower()}@{company_name.lower().replace(' ', '')}.com",
        city=city,
        country=country,
        extra_fields=extra_fields or {},
        source_file="leads.csv",
        source_row=source_row,
    )


def _company(name, industry, city, country, source_row):
    return CompanyProspect(
        company_name=name,
        company_domain=f"{name.lower().replace(' ', '')}.com",
        company_website=f"https://{name.lower().replace(' ', '')}.com",
        industry=industry,
        company_size="51-200",
        city=city,
        country=country,
        description="A great company",
        source_file="companies.csv",
        source_row=source_row,
    )


def _campaign_definition(criteria, queries):
    spec = CampaignSpec(
        target_type=TargetType.PERSON,
        objective="Find prospects",
        target_description="Target prospects",
        criteria=criteria,
    )
    plan = QueryPlan(queries=queries)
    return CampaignDefinition(
        original_prompt="test",
        spec=spec,
        query_plan=plan,
        status=CampaignStatus.READY,
    )


def _requirement_country(country: str) -> Criterion:
    return Criterion(
        id="c1",
        description=f"Must be in {country}",
        kind=CriterionKind.REQUIREMENT,
        evaluation_mode=EvaluationMode.STRUCTURED,
        predicate=FieldPredicate(
            field=PredicateField.COUNTRY,
            operator=PredicateOperator.EQ,
            value=country,
        ),
    )


def test_pipeline_returns_ranked_candidates():
    prospects = [
        _prospect("John Smith", "Acme Corp", "Sydney", "Australia", 2),
        _prospect("Jane Doe", "Globex", "Melbourne", "Australia", 3),
    ]
    criteria = [_requirement_country("Australia")]
    queries = [
        SearchQuery(
            id="q1",
            query="Sydney engineer",
            facet=SearchFacet.ROLE,
            rationale="Find engineers in Sydney",
        ),
        SearchQuery(
            id="q2",
            query="Melbourne engineer",
            facet=SearchFacet.ROLE,
            rationale="Find engineers in Melbourne",
        ),
    ]
    campaign = _campaign_definition(criteria, queries)
    output = run(prospects, campaign, top_n=10)
    assert len(output.candidates) == 2
    assert output.total_scanned == 2
    assert output.tier1_passed == 2
    assert output.queries_executed == 2
    assert output.candidates[0].rank == 1
    assert output.candidates[1].rank == 2


def test_pipeline_tier1_filters_out_non_matching():
    prospects = [
        _prospect("John Smith", "Acme Corp", "Sydney", "Australia", 2),
        _prospect("Jane Doe", "Globex", "London", "UK", 3),
    ]
    criteria = [_requirement_country("Australia")]
    queries = [
        SearchQuery(
            id="q1",
            query="engineer",
            facet=SearchFacet.ROLE,
            rationale="Find engineers",
        ),
    ]
    campaign = _campaign_definition(criteria, queries)
    output = run(prospects, campaign, top_n=10)
    assert output.tier1_passed == 1
    assert len(output.candidates) == 1
    assert output.candidates[0].prospect_data["city"] == "Sydney"


def test_pipeline_with_company_prospects():
    prospects = [
        _company("Acme Corp", "SaaS", "Sydney", "Australia", 2),
        _company("Globex", "Marketing", "Melbourne", "Australia", 3),
    ]
    criteria = [_requirement_country("Australia")]
    queries = [
        SearchQuery(
            id="q1",
            query="SaaS company",
            facet=SearchFacet.INDUSTRY,
            rationale="Find SaaS companies",
        ),
    ]
    campaign = _campaign_definition(criteria, queries)
    output = run(prospects, campaign, top_n=10)
    assert output.tier1_passed == 2
    assert len(output.candidates) == 2
    assert output.candidates[0].prospect_type == "company"


def test_pipeline_empty_prospects():
    criteria = [_requirement_country("Australia")]
    queries = [
        SearchQuery(
            id="q1",
            query="test",
            facet=SearchFacet.OTHER,
            rationale="test",
        ),
    ]
    campaign = _campaign_definition(criteria, queries)
    output = run([], campaign, top_n=10)
    assert output.candidates == []
    assert output.total_scanned == 0


def test_pipeline_no_queries_returns_tier1_results():
    prospects = [
        _prospect("John Smith", "Acme Corp", "Sydney", "Australia", 2),
    ]
    criteria = [_requirement_country("Australia")]
    queries = [
        SearchQuery(
            id="q1",
            query="engineer",
            facet=SearchFacet.ROLE,
            rationale="Find engineers",
        ),
    ]
    campaign = _campaign_definition(criteria, queries)
    output = run(prospects, campaign, top_n=10)
    assert output.tier1_passed == 1
    assert len(output.candidates) == 1
    assert output.queries_executed == 1


def test_pipeline_respects_top_n():
    prospects = [
        _prospect(f"Person {i}", f"Co {i}", "Sydney", "Australia", i + 2)
        for i in range(5)
    ]
    criteria = [_requirement_country("Australia")]
    queries = [
        SearchQuery(
            id="q1",
            query="person",
            facet=SearchFacet.ROLE,
            rationale="Find people",
        ),
    ]
    campaign = _campaign_definition(criteria, queries)
    output = run(prospects, campaign, top_n=3)
    assert len(output.candidates) == 3


def test_pipeline_does_not_mutate_input():
    prospects = [
        _prospect("John Smith", "Acme Corp", "Sydney", "Australia", 2),
    ]
    original = list(prospects)
    criteria = [_requirement_country("Australia")]
    queries = [
        SearchQuery(
            id="q1",
            query="engineer",
            facet=SearchFacet.ROLE,
            rationale="Find engineers",
        ),
    ]
    campaign = _campaign_definition(criteria, queries)
    run(prospects, campaign, top_n=10)
    assert prospects == original


def test_pipeline_semantic_criteria_not_applied_in_tier1():
    prospects = [
        _prospect("John Smith", "Acme Corp", "Sydney", "Australia", 2),
        _prospect("Jane Doe", "Globex", "London", "UK", 3),
    ]
    criteria = [
        Criterion(
            id="c1",
            description="Company is innovative",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.SEMANTIC,
            predicate=None,
        ),
    ]
    queries = [
        SearchQuery(
            id="q1",
            query="engineer",
            facet=SearchFacet.ROLE,
            rationale="Find engineers",
        ),
    ]
    campaign = _campaign_definition(criteria, queries)
    output = run(prospects, campaign, top_n=10)
    # Semantic criteria not applied in Tier 1, so both pass
    assert output.tier1_passed == 2
