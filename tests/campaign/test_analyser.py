import json

import pytest

from nirite.campaign import analyser as analyser_module
from nirite.campaign.analyser import CampaignAnalyser


def analysis_json(objective: str) -> str:
    return json.dumps({
        "target_type": "company",
        "objective": objective,
        "target_description": "Logistics companies",
        "explicit_criteria": [{
            "id": "C1",
            "description": "Logistics",
            "kind": "requirement",
            "source_phrase": "logistics",
        }],
        "ambiguities": [],
    })


class FakeProvider:
    def __init__(self, objective, delay=0.0, error=None):
        self.objective, self.delay, self.error = objective, delay, error
        self.calls = 0

    def generate_json(self, system_prompt, user_prompt, schema):
        self.calls += 1
        if self.error:
            raise self.error
        return analysis_json(self.objective)


class Err503(Exception):
    status_code = 503


def test_primary_provider_result_returned():
    """Ministral (primary) succeeds — its analysis is returned, backup not called."""
    primary = FakeProvider("primary")
    backup = FakeProvider("backup")
    results = CampaignAnalyser([("Primary", primary), ("Backup", backup)]).analyse("x")
    assert [r.objective for r in results] == ["primary"]
    assert primary.calls == 1
    assert backup.calls == 0  # backup never invoked


def test_fallback_used_when_primary_fails():
    """Primary errors — backup (Gemini) result is returned."""
    primary = FakeProvider("primary", error=ValueError("boom"))
    backup = FakeProvider("backup")
    results = CampaignAnalyser([("Primary", primary), ("Backup", backup)]).analyse("x")
    assert [r.objective for r in results] == ["backup"]
    assert primary.calls == 1
    assert backup.calls == 1


def test_all_providers_fail_raises():
    """Both primary and backup fail — RuntimeError raised."""
    primary = FakeProvider("primary", error=ValueError("boom"))
    backup = FakeProvider("backup", error=ValueError("boom"))
    with pytest.raises(RuntimeError, match="couldn't get a campaign analysis"):
        CampaignAnalyser([("Primary", primary), ("Backup", backup)]).analyse("x")


def test_primary_retried_on_503_then_fallback(monkeypatch):
    """Primary fails with 503 MAX_ATTEMPTS times, then fallback succeeds."""
    monkeypatch.setattr(analyser_module.time, "sleep", lambda _: None)
    flaky = FakeProvider("primary", error=Err503())
    backup = FakeProvider("backup")
    results = CampaignAnalyser([("Primary", flaky), ("Backup", backup)]).analyse("x")
    assert [r.objective for r in results] == ["backup"]
    assert flaky.calls == analyser_module.MAX_ATTEMPTS
    assert backup.calls == 1


def test_invalid_primary_output_falls_back_to_backup():
    """Primary returns invalid JSON/schema — fallback's valid result is used."""
    bad = json.loads(analysis_json("bad"))
    bad["ambiguities"] = [{
        "id": "A1", "topic": "size", "original_term": "mid",
        "question": "?", "affected_criterion_ids": ["NOPE"],
    }]

    class BadProvider(FakeProvider):
        def generate_json(self, system_prompt, user_prompt, schema):
            self.calls += 1
            return json.dumps(bad)

    primary = BadProvider("primary")
    backup = FakeProvider("backup")
    results = CampaignAnalyser([("Primary", primary), ("Backup", backup)]).analyse("x")
    assert [r.objective for r in results] == ["backup"]
    assert primary.calls == 1
    assert backup.calls == 1


def test_empty_providers_raises():
    """No providers configured — ValueError raised."""
    with pytest.raises(ValueError, match="No analysis providers configured"):
        CampaignAnalyser([]).analyse("x")
