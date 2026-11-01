import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nirite.campaign.parser import CampaignParser

@pytest.fixture
def mock_client():
    return MagicMock()

@pytest.fixture
def parser(mock_client):
    return CampaignParser(client=mock_client)

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
                        "field": "location",
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

def mock_completion(content):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content)
            )
        ]
    )

def test_parse_valid_campaign(parser, mock_client, valid_response):
    prompt = "Find Australian SaaS companies selling to mid-market businesses."

    mock_client.chat.completions.create.return_value = mock_completion(
        json.dumps(valid_response)
    )

    result = parser.parse(prompt)

    assert result.original_prompt == prompt
    assert result.spec.target_type == "company"
    assert len(result.spec.criteria) == 2
    assert len(result.query_plan.queries) == 2
    assert result.status == "ready"

    mock_client.chat.completions.create.assert_called_once()

def test_parse_rejects_empty_prompt(parser):
    with pytest.raises(ValueError, match="cannot be empty"):
        parser.parse("   ")

def test_parse_rejects_empty_response(parser, mock_client):
    mock_client.chat.completions.create.return_value = mock_completion(None)

    with pytest.raises(ValueError, match="No content returned from model"):
        parser.parse("Find Australian SaaS companies")

def test_parse_rejects_invalid_json(parser, mock_client):
    mock_client.chat.completions.create.return_value = mock_completion(
        "This is not JSON"
    )

    with pytest.raises(ValueError, match="does not conform to expected schema"):
        parser.parse("Find Australian SaaS companies")

def test_parse_rejects_invalid_campaign_schema(parser, mock_client):
    invalid_response = {
        "original_prompt": "Test",
        "spec": {},
        "query_plan": {"queries": []},
        "status": "ready",
    }

    mock_client.chat.completions.create.return_value = mock_completion(
        json.dumps(invalid_response)
    )

    with pytest.raises(ValueError, match="does not conform to expected schema"):
        parser.parse("Find Australian SaaS companies")

def test_parse_overwrites_model_original_prompt(
    parser,
    mock_client,
    valid_response,
):
    prompt = "Find fintech companies in Singapore."

    mock_client.chat.completions.create.return_value = mock_completion(
        json.dumps(valid_response)
    )

    result = parser.parse(prompt)

    assert result.original_prompt == prompt
