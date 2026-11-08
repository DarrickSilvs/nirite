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
    return CampaignParser(providers=[("mock", mock_provider)])


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

    with pytest.raises(RuntimeError, match="couldn't parse the campaign"):
        parser.parse("Find Australian SaaS companies", valid_analyses)


def test_parse_rejects_invalid_json(parser, mock_provider, valid_analyses):
    mock_provider.generate_json.return_value = "This is not JSON"

    with pytest.raises(RuntimeError, match="couldn't parse the campaign"):
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

    with pytest.raises(RuntimeError, match="couldn't parse the campaign"):
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


def test_parser_assigns_stable_ids_and_remaps_clarifications(
    parser, mock_provider, valid_response, valid_analyses
):
    valid_response["spec"]["criteria"][0]["id"] = "country_rule"
    valid_response["spec"]["criteria"][1]["id"] = "CRIT-B"
    valid_response["query_plan"]["queries"][0]["id"] = "alpha"
    valid_response["query_plan"]["queries"][1]["id"] = "beta"
    valid_response["clarifications"] = [{
        "question": "What is mid-market?",
        "reason": "Size undefined",
        "related_criterion_ids": ["CRIT-B"],
    }]
    mock_provider.generate_json.return_value = json.dumps(valid_response)

    result = parser.parse("Find Australian SaaS companies.", valid_analyses)

    assert [c.id for c in result.spec.criteria] == ["c1", "c2"]
    assert [q.id for q in result.query_plan.queries] == ["q1", "q2"]
    assert result.clarifications[0].related_criterion_ids == ["c2"]
    assert result.status == "needs_clarification"


def test_parser_rejects_clarification_with_dangling_reference(
    parser, mock_provider, valid_response, valid_analyses
):
    valid_response["clarifications"] = [{
        "question": "?", "reason": "r", "related_criterion_ids": ["ghost"],
    }]
    mock_provider.generate_json.return_value = json.dumps(valid_response)

    with pytest.raises(RuntimeError, match="couldn't parse the campaign"):
        parser.parse("Find Australian SaaS companies.", valid_analyses)


def test_parser_repair_retry_can_succeed(
    parser, mock_provider, valid_response, valid_analyses
):
    mock_provider.generate_json.side_effect = [
        "not json at all",
        json.dumps(valid_response),
    ]
    result = parser.parse("Find Australian SaaS companies.", valid_analyses)
    assert result.status == "ready"
    assert mock_provider.generate_json.call_count == 2
