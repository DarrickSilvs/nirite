import json
from unittest.mock import MagicMock

import pytest

from nirite.campaign.parser import CampaignParser
from nirite.models.campaign import CriterionKind
from nirite.models.campaign_analysis import CampaignAnalysis, AnalysisCriterion


@pytest.fixture
def mock_provider():
    return MagicMock()

@pytest.fixture
def parser(mock_provider):
    return CampaignParser(provider=mock_provider)

@pytest.fixture
def valid_analyses():
    return [
        CampaignAnalysis(
            target_type="company",
            objective="Find suitable SaaS companies",
            target_description="Australian SaaS companies",
            explicit_criteria=[
                AnalysisCriterion(
                    id="saas",
                    description="Company provides SaaS products",
                    kind=CriterionKind.REQUIREMENT,
                    source_phrase="SaaS companies",
                )
            ],
            ambiguities=[],
        )
    ]

@pytest.fixture
def valid_response():
    return {
        "original_prompt": "Incorrect original prompt",
        "spec": {
            "target_type": "company",
            "objective": "Find suitable SaaS prospects",
            "target_description": (
                "Australian SaaS companies selling to mid-market businesses"
            ),
            "criteria": [
                {
                    "id": "c1",
                    "description": "Must be based in Australia",
                    "kind": "requirement",
                    "evaluation_mode": "structured",
                    "predicate": {
                        "field": "country",
                        "operator": "contains",
                        "value": "Australia",
                    },
                },
                {
                    "id": "c2",
                    "description": "Sells to mid-market businesses",
                    "kind": "requirement",
                    "evaluation_mode": "semantic",
                },
            ],
        },
        "query_plan": {
            "queries": [
                {
                    "id": "q1",
                    "query": "Australian B2B SaaS companies",
                    "facet": "industry",
                    "rationale": "Find relevant SaaS businesses",
                },
                {
                    "id": "q2",
                    "query": "Australian software companies serving mid-market",
                    "facet": "customer_type",
                    "rationale": "Find companies with the desired customer base",
                },
            ],
        },
        "status": "ready",
    }

def test_parse_valid_campaign(
    parser,
    mock_provider,
    valid_response,
    valid_analyses,
):
    prompt = "Find Australian SaaS companies selling to mid-market businesses."

    mock_provider.generate_json.return_value = json.dumps(valid_response)

    result = parser.parse(prompt, valid_analyses)

    assert result.original_prompt == prompt
    assert result.spec.target_type == "company"
    assert len(result.spec.criteria) == 2
    assert len(result.query_plan.queries) == 2
    assert result.status == "ready"

    mock_provider.generate_json.assert_called_once()

def test_parse_rejects_empty_prompt(parser, valid_analyses):
    with pytest.raises(ValueError, match="cannot be empty"):
        parser.parse("   ", valid_analyses)

def test_parse_rejects_empty_response(parser, mock_provider, valid_analyses):
    mock_provider.generate_json.return_value = ""

    with pytest.raises(ValueError, match="No content returned from model"):
        parser.parse("Find Australian SaaS companies", valid_analyses)

def test_parse_rejects_invalid_json(parser, mock_provider, valid_analyses):
    mock_provider.generate_json.return_value = "This is not JSON"

    with pytest.raises(ValueError, match="invalid JSON"):
        parser.parse("Find Australian SaaS companies", valid_analyses)

def test_parse_rejects_invalid_campaign_schema(
    parser,
    mock_provider,
    valid_analyses,
):
    invalid_response = {
        "original_prompt": "Test",
        "spec": {},
        "query_plan": {"queries": []},
        "status": "ready",
    }

    mock_provider.generate_json.return_value = json.dumps(invalid_response)

    with pytest.raises(ValueError, match="did not conform to the schema after one retry"):
        parser.parse("Find Australian SaaS companies", valid_analyses)

def test_parse_overwrites_model_original_prompt(
    parser,
    mock_provider,
    valid_response,
    valid_analyses,
):
    prompt = "Find fintech companies in Singapore."

    mock_provider.generate_json.return_value = json.dumps(valid_response)

    result = parser.parse(prompt, valid_analyses)

    assert result.original_prompt == prompt

def test_parse_passes_analyses_to_provider(
    parser,
    mock_provider,
    valid_response,
    valid_analyses,
):
    prompt = "Find Australian SaaS companies."

    mock_provider.generate_json.return_value = json.dumps(valid_response)

    parser.parse(prompt, valid_analyses)

    user_prompt = mock_provider.generate_json.call_args.kwargs["user_prompt"]

    assert prompt in user_prompt
    assert "suitable SaaS companies" in user_prompt
