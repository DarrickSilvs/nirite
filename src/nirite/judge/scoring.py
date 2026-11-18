"""Fixed scoring math for bounded-judge verdicts.

No thresholds here — policy lives with callers. ``score = yes_count /
total``; ``unknown`` counts as non-yes. Polarity inverts meaning for
aggregation only (exclusion criteria).
"""

from __future__ import annotations

from nirite.judge.models import (
    JudgeAnswer,
    JudgeAnswerValue,
    JudgePolarity,
    JudgeQuestion,
)


class JudgeScoringError(ValueError):
    """Raised when answers don't match questions (duplicate, missing, or extra)."""


def score_verdict(
    questions: list[JudgeQuestion],
    answers: list[JudgeAnswer],
) -> float:
    """Compute fixed score = yes_count / total_questions.

    Validates that answers match questions one-to-one. ``unknown`` answers
    count as non-yes. Polarity inverts: for NEGATIVE questions, ``yes``
    means the criterion is NOT met (counts as non-yes), ``no`` means met
    (counts as yes).
    """
    if not questions:
        return 0.0

    question_ids = {q.id for q in questions}
    answer_ids = [a.question_id for a in answers]

    # Duplicate answer ids
    if len(answer_ids) != len(set(answer_ids)):
        raise JudgeScoringError("duplicate answer question_id")

    # Missing answers
    missing = question_ids - set(answer_ids)
    if missing:
        raise JudgeScoringError(f"missing answers for questions: {sorted(missing)}")

    # Extra answers
    extra = set(answer_ids) - question_ids
    if extra:
        raise JudgeScoringError(f"answers for unknown questions: {sorted(extra)}")

    answer_map = {a.question_id: a for a in answers}

    yes_count = 0
    for question in questions:
        answer = answer_map[question.id]
        is_yes = _is_yes(question, answer)
        if is_yes:
            yes_count += 1

    return yes_count / len(questions)


def _is_yes(question: JudgeQuestion, answer: JudgeAnswer) -> bool:
    """Determine if an answer counts as 'yes' given the question polarity."""
    if answer.answer == JudgeAnswerValue.UNKNOWN:
        return False
    if answer.answer == JudgeAnswerValue.YES:
        return question.polarity == JudgePolarity.POSITIVE
    # answer == NO
    return question.polarity == JudgePolarity.NEGATIVE


def aggregate_scores(scores: list[float]) -> float:
    """Average a list of scores. Returns 0.0 for empty list."""
    if not scores:
        return 0.0
    return sum(scores) / len(scores)
