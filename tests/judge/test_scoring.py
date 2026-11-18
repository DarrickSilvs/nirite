"""Tests for judge scoring math (TASK-07)."""

from __future__ import annotations

import pytest

from nirite.judge.models import (
    JudgeAnswer,
    JudgeAnswerValue,
    JudgePolarity,
    JudgeQuestion,
    JudgeVerdict,
)
from nirite.judge.scoring import JudgeScoringError, aggregate_scores, score_verdict


def _question(
    qid: str, text: str, polarity: JudgePolarity = JudgePolarity.POSITIVE
) -> JudgeQuestion:
    return JudgeQuestion(
        id=qid,
        text=text,
        criterion_id="c1",
        polarity=polarity,
    )


def _answer(qid: str, answer: JudgeAnswerValue) -> JudgeAnswer:
    return JudgeAnswer(
        question_id=qid,
        answer=answer,
    )


def test_all_yes_score_is_one() -> None:
    questions = [_question("q1", "Is it met?"), _question("q2", "Is it met?")]
    answers = [_answer("q1", JudgeAnswerValue.YES), _answer("q2", JudgeAnswerValue.YES)]
    assert score_verdict(questions, answers) == 1.0


def test_all_no_score_is_zero() -> None:
    questions = [_question("q1", "Is it met?"), _question("q2", "Is it met?")]
    answers = [_answer("q1", JudgeAnswerValue.NO), _answer("q2", JudgeAnswerValue.NO)]
    assert score_verdict(questions, answers) == 0.0


def test_unknown_counts_as_non_yes() -> None:
    questions = [_question("q1", "Is it met?"), _question("q2", "Is it met?")]
    answers = [
        _answer("q1", JudgeAnswerValue.YES),
        _answer("q2", JudgeAnswerValue.UNKNOWN),
    ]
    assert score_verdict(questions, answers) == 0.5


def test_mixed_score() -> None:
    questions = [
        _question("q1", "Is it met?"),
        _question("q2", "Is it met?"),
        _question("q3", "Is it met?"),
    ]
    answers = [
        _answer("q1", JudgeAnswerValue.YES),
        _answer("q2", JudgeAnswerValue.NO),
        _answer("q3", JudgeAnswerValue.UNKNOWN),
    ]
    assert score_verdict(questions, answers) == 1.0 / 3.0


def test_negative_polarity_inverts() -> None:
    """For exclusion criteria, yes means NOT met (non-yes), no means met (yes)."""
    questions = [
        _question("q1", "Is it excluded?", polarity=JudgePolarity.NEGATIVE),
        _question("q2", "Is it excluded?", polarity=JudgePolarity.NEGATIVE),
    ]
    answers = [
        _answer("q1", JudgeAnswerValue.NO),  # not excluded -> met -> yes
        _answer("q2", JudgeAnswerValue.YES),  # excluded -> not met -> non-yes
    ]
    assert score_verdict(questions, answers) == 0.5


def test_empty_questions_score_is_zero() -> None:
    assert score_verdict([], []) == 0.0


def test_duplicate_answer_ids_raise() -> None:
    questions = [_question("q1", "Is it met?")]
    answers = [
        _answer("q1", JudgeAnswerValue.YES),
        _answer("q1", JudgeAnswerValue.NO),
    ]
    with pytest.raises(JudgeScoringError, match="duplicate"):
        score_verdict(questions, answers)


def test_missing_answer_raises() -> None:
    questions = [_question("q1", "Is it met?"), _question("q2", "Is it met?")]
    answers = [_answer("q1", JudgeAnswerValue.YES)]
    with pytest.raises(JudgeScoringError, match="missing"):
        score_verdict(questions, answers)


def test_extra_answer_raises() -> None:
    questions = [_question("q1", "Is it met?")]
    answers = [
        _answer("q1", JudgeAnswerValue.YES),
        _answer("q2", JudgeAnswerValue.NO),
    ]
    with pytest.raises(JudgeScoringError, match="unknown"):
        score_verdict(questions, answers)


def test_aggregate_scores() -> None:
    assert aggregate_scores([1.0, 0.0, 0.5]) == 0.5
    assert aggregate_scores([]) == 0.0
    assert aggregate_scores([1.0]) == 1.0


def test_judge_verdict_model() -> None:
    verdict = JudgeVerdict(
        criterion_id="c1",
        answers=[
            JudgeAnswer(question_id="q1", answer=JudgeAnswerValue.YES),
            JudgeAnswer(question_id="q2", answer=JudgeAnswerValue.NO),
        ],
        score=0.5,
        rationale_code="partial_match",
    )
    assert verdict.criterion_id == "c1"
    assert verdict.score == 0.5
    assert verdict.rationale_code == "partial_match"
    assert len(verdict.answers) == 2
