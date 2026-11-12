"""Tests for retrieval agents (ListRetrievalAgent, SemanticRetrievalAgent)."""

import pytest

from nirite.models.company import CompanyProspect
from nirite.models.prospect import Prospect

from nirite.retrieval.agents import ListRetrievalAgent, SemanticRetrievalAgent


@pytest.fixture
def individual_prospects():
    return [
        Prospect(
            full_name="John Smith",
            first_name="John",
            last_name="Smith",
            job_title="Software Engineer",
            company_name="Acme Corp",
            company_domain="acme.com",
            company_website="https://acme.com",
            email="john@acme.com",
            city="Sydney",
            state="NSW",
            country="Australia",
            source_file="leads.csv",
            source_row=2,
        ),
        Prospect(
            full_name="Jane Doe",
            first_name="Jane",
            last_name="Doe",
            job_title="Marketing Manager",
            company_name="Globex",
            company_domain="globex.com",
            company_website="https://globex.com",
            email="jane@globex.com",
            city="Melbourne",
            state="VIC",
            country="Australia",
            source_file="leads.csv",
            source_row=3,
        ),
        Prospect(
            full_name="Bob Wilson",
            first_name="Bob",
            last_name="Wilson",
            job_title="Sales Rep",
            company_name="TestCo",
            company_domain="testco.com",
            company_website="https://testco.com",
            email="bob@testco.com",
            city="Brisbane",
            state="QLD",
            country="Australia",
            source_file="leads.csv",
            source_row=4,
        ),
    ]


@pytest.fixture
def company_prospects():
    return [
        CompanyProspect(
            company_name="Acme Corp",
            company_domain="acme.com",
            company_website="https://acme.com",
            industry="SaaS",
            company_size="51-200",
            city="Sydney",
            country="Australia",
            description="B2B SaaS platform for workflow automation",
            source_file="companies.csv",
            source_row=2,
        ),
        CompanyProspect(
            company_name="Globex",
            company_domain="globex.com",
            company_website="https://globex.com",
            industry="Marketing",
            company_size="11-50",
            city="Melbourne",
            country="Australia",
            description="Digital marketing agency serving e-commerce brands",
            source_file="companies.csv",
            source_row=3,
        ),
        CompanyProspect(
            company_name="TestCo",
            company_domain="testco.com",
            company_website="https://testco.com",
            industry="Retail",
            company_size="1-10",
            city="Brisbane",
            country="Australia",
            description="Online retail store for home goods",
            source_file="companies.csv",
            source_row=4,
        ),
    ]


# --- ListRetrievalAgent tests ---

def test_list_retrieval_agent_returns_ranked_entries(individual_prospects):
    agent = ListRetrievalAgent()
    results = agent.retrieve(individual_prospects, "Sydney software engineer", "q1")
    # Only John Smith matches (Sydney + software + engineer); Jane and Bob score 0
    assert len(results) == 1
    entry = results[0]
    assert entry.rank == 1
    assert entry.score == 3.0
    assert entry.prospect_data["city"] == "Sydney"
    assert entry.prospect_type == "individual"


def test_list_retrieval_agent_matches_keywords(individual_prospects):
    agent = ListRetrievalAgent()
    results = agent.retrieve(individual_prospects, "Sydney", "q1")
    # Sydney prospect should rank first
    assert results[0].prospect_data["city"] == "Sydney"


def test_list_retrieval_agent_skips_zero_match_prospects(individual_prospects):
    agent = ListRetrievalAgent()
    results = agent.retrieve(individual_prospects, "Sydney", "q1")
    # Jane (Melbourne) and Bob (Brisbane) match nothing and are excluded
    assert len(results) == 1
    assert results[0].prospect_data["city"] == "Sydney"
    assert results[0].score == 1.0


def test_list_retrieval_agent_empty_query_returns_none(individual_prospects):
    agent = ListRetrievalAgent()
    results = agent.retrieve(individual_prospects, "", "q1")
    assert results == []


def test_list_retrieval_agent_empty_prospects_returns_empty():
    agent = ListRetrievalAgent()
    results = agent.retrieve([], "anything", "q1")
    assert results == []


def test_list_retrieval_agent_case_insensitive(individual_prospects):
    agent = ListRetrievalAgent()
    results_lower = agent.retrieve(individual_prospects, "sydney", "q1")
    results_upper = agent.retrieve(individual_prospects, "SYDNEY", "q1")
    assert results_lower[0].prospect_data["city"] == results_upper[0].prospect_data["city"]


def test_list_retrieval_agent_does_not_mutate_input(individual_prospects):
    original = list(individual_prospects)
    agent = ListRetrievalAgent()
    agent.retrieve(individual_prospects, "Sydney", "q1")
    assert individual_prospects == original


# --- SemanticRetrievalAgent tests ---

def test_semantic_retrieval_agent_returns_ranked_entries(individual_prospects):
    agent = SemanticRetrievalAgent()
    results = agent.retrieve(individual_prospects, "software engineer Sydney", "q1")
    # Only John Smith matches; Jane and Bob have zero similarity
    assert len(results) == 1
    entry = results[0]
    assert entry.rank == 1
    assert entry.score > 0.0
    assert entry.prospect_data["full_name"] == "John Smith"
    assert entry.prospect_type == "individual"


def test_semantic_retrieval_agent_ranks_relevant_first(individual_prospects):
    agent = SemanticRetrievalAgent()
    results = agent.retrieve(individual_prospects, "software engineer", "q1")
    # John Smith is a Software Engineer, should rank highly
    assert results[0].prospect_data["full_name"] == "John Smith"


def test_semantic_retrieval_agent_skips_zero_similarity_prospects(individual_prospects):
    agent = SemanticRetrievalAgent()
    results = agent.retrieve(individual_prospects, "Sydney", "q1")
    # Jane (Melbourne) and Bob (Brisbane) share no terms with the query
    assert len(results) == 1
    assert results[0].prospect_data["city"] == "Sydney"
    assert results[0].score > 0.0


def test_semantic_retrieval_agent_empty_query_returns_none(individual_prospects):
    agent = SemanticRetrievalAgent()
    results = agent.retrieve(individual_prospects, "", "q1")
    assert results == []


def test_semantic_retrieval_agent_empty_prospects_returns_empty():
    agent = SemanticRetrievalAgent()
    results = agent.retrieve([], "anything", "q1")
    assert results == []


def test_semantic_retrieval_agent_with_company_prospects(company_prospects):
    agent = SemanticRetrievalAgent()
    results = agent.retrieve(company_prospects, "SaaS automation platform", "q1")
    # Only Acme Corp matches; Globex and TestCo share no terms with the query
    assert len(results) == 1
    assert results[0].prospect_data["company_name"] == "Acme Corp"
    assert results[0].score > 0.0


def test_semantic_retrieval_agent_case_insensitive(individual_prospects):
    agent = SemanticRetrievalAgent()
    results_lower = agent.retrieve(individual_prospects, "sydney", "q1")
    results_upper = agent.retrieve(individual_prospects, "SYDNEY", "q1")
    assert results_lower[0].prospect_data["city"] == results_upper[0].prospect_data["city"]


def test_semantic_retrieval_agent_does_not_mutate_input(individual_prospects):
    original = list(individual_prospects)
    agent = SemanticRetrievalAgent()
    agent.retrieve(individual_prospects, "Sydney", "q1")
    assert individual_prospects == original
