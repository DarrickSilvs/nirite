"""Tests for batched judge client (TASK-08)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nirite.judge.client import MAX_QUESTIONS_PER_CALL, JudgeClient, JudgeError
from nirite.judge.models import JudgeAnswerValue, JudgeQuestion
from tests.support.fakes import FakeLLMProvider


def _question(qid: str) -> JudgeQuestion:
    return JudgeQuestion(
        id=qid,
        text=f"Question {qid}?",
        criterion_id="c1",
        answerable_from=["field1"],
    )


def _make_client(
    provider: FakeLLMProvider, cache_dir: Path | None = None
) -> JudgeClient:
    return JudgeClient(provider, cache_dir=cache_dir)


def test_happy_path() -> None:
    provider = FakeLLMProvider(
        responses=[
            json.dumps(
                {
                    "answers": [
                        {
                            "question_id": "q1",
                            "answer": "yes",
                            "evidence_field": "field1",
                            "evidence_quote": "some value",
                        }
                    ]
                }
            )
        ]
    )
    client = _make_client(provider)
    questions = [_question("q1")]
    answers = client.judge(questions, {"field1": "some value"})
    assert len(answers) == 1
    assert answers[0].question_id == "q1"
    assert answers[0].answer == JudgeAnswerValue.YES
    assert provider.call_count == 1


def test_malformed_then_retry_success() -> None:
    provider = FakeLLMProvider(
        responses=[
            "not valid json at all",
            json.dumps(
                {
                    "answers": [
                        {
                            "question_id": "q1",
                            "answer": "no",
                            "evidence_field": None,
                            "evidence_quote": None,
                        }
                    ]
                }
            ),
        ]
    )
    client = _make_client(provider)
    questions = [_question("q1")]
    answers = client.judge(questions, {"field1": "value"})
    assert len(answers) == 1
    assert answers[0].answer == JudgeAnswerValue.NO
    assert provider.call_count == 2


def test_malformed_twice_raises_judge_error() -> None:
    provider = FakeLLMProvider(
        responses=["bad json", "also bad"],
    )
    client = _make_client(provider)
    questions = [_question("q1")]
    with pytest.raises(JudgeError):
        client.judge(questions, {"field1": "value"})
    assert provider.call_count == 2


def test_cache_hit_zero_provider_calls(tmp_path) -> None:
    provider = FakeLLMProvider(
        responses=[
            json.dumps(
                {
                    "answers": [
                        {
                            "question_id": "q1",
                            "answer": "yes",
                            "evidence_field": None,
                            "evidence_quote": None,
                        }
                    ]
                }
            )
        ]
    )
    client = _make_client(provider, cache_dir=tmp_path)
    questions = [_question("q1")]

    # First call hits the provider
    answers1 = client.judge(questions, {"field1": "value"})
    assert provider.call_count == 1

    # Second call uses cache
    answers2 = client.judge(questions, {"field1": "value"})
    assert provider.call_count == 1  # no additional call
    assert answers1 == answers2


def test_question_budget_breach_raises() -> None:
    provider = FakeLLMProvider(responses=["{}"])
    client = _make_client(provider)
    questions = [_question(f"q{i}") for i in range(MAX_QUESTIONS_PER_CALL + 1)]
    with pytest.raises(JudgeError, match="exceeds"):
        client.judge(questions, {"field1": "value"})
    assert provider.call_count == 0  # no call made


def test_atomic_cache_write(tmp_path) -> None:
    provider = FakeLLMProvider(
        responses=[
            json.dumps(
                {
                    "answers": [
                        {
                            "question_id": "q1",
                            "answer": "unknown",
                            "evidence_field": None,
                            "evidence_quote": None,
                        }
                    ]
                }
            )
        ]
    )
    client = _make_client(provider, cache_dir=tmp_path)
    questions = [_question("q1")]
    client.judge(questions, {"field1": "value"})

    # Cache file exists and contains expected data
    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1
    data = json.loads(cache_files[0].read_text())
    assert len(data) == 1
    assert data[0]["answer"] == "unknown"

    # No .tmp files left behind
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert len(tmp_files) == 0
