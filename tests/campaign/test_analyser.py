import json
import time

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
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return analysis_json(self.objective)


class Err503(Exception):
    status_code = 503


def test_results_are_ordered_by_provider_name_not_completion_time():
    providers = [
        ("Zeta", FakeProvider("zeta", delay=0.0)),
        ("Alpha", FakeProvider("alpha", delay=0.15)),
        ("Mid", FakeProvider("mid", delay=0.05)),
    ]
    results = CampaignAnalyser(providers).analyse("find logistics")
    assert [r.objective for r in results] == ["alpha", "mid", "zeta"]


def test_two_of_three_is_enough():
    providers = [
        ("A", FakeProvider("a")),
        ("B", FakeProvider("b", error=ValueError("boom"))),
        ("C", FakeProvider("c")),
    ]
    assert len(CampaignAnalyser(providers).analyse("x")) == 2


def test_one_of_three_raises():
    providers = [
        ("A", FakeProvider("a")),
        ("B", FakeProvider("b", error=ValueError("boom"))),
        ("C", FakeProvider("c", error=ValueError("boom"))),
    ]
    with pytest.raises(RuntimeError, match="couldn't get enough"):
        CampaignAnalyser(providers).analyse("x")


def test_503_is_retried_then_fails_after_max_attempts(monkeypatch):
    monkeypatch.setattr(analyser_module.time, "sleep", lambda _: None)
    flaky = FakeProvider("x", error=Err503())
    providers = [("A", flaky), ("B", FakeProvider("b")), ("C", FakeProvider("c"))]

    assert len(CampaignAnalyser(providers).analyse("x")) == 2
    assert flaky.calls == analyser_module.MAX_ATTEMPTS


def test_analysis_with_unknown_affected_criterion_is_rejected(monkeypatch):
    bad = json.loads(analysis_json("bad"))
    bad["ambiguities"] = [{
        "id": "A1", "topic": "size", "original_term": "mid",
        "question": "?", "affected_criterion_ids": ["NOPE"],
    }]

    class BadProvider(FakeProvider):
        def generate_json(self, *a, **k):
            return json.dumps(bad)

    providers = [("A", BadProvider("a")), ("B", FakeProvider("b")), ("C", FakeProvider("c"))]
    assert len(CampaignAnalyser(providers).analyse("x")) == 2
