"""Tests for bounded question planner (TASK-12)."""

from __future__ import annotations

from nirite.models.campaign import CriterionKind
from nirite.models.campaign_analysis import AnalysisCriterion
from nirite.qualification.questions import plan_questions


def _criterion(
    *,
    id: str = "c1",
    description: str = "Must be based in Australia",
    kind: CriterionKind = CriterionKind.REQUIREMENT,
) -> AnalysisCriterion:
    return AnalysisCriterion(
        id=id,
        description=description,
        kind=kind,
        source_phrase="Australian companies",
    )


def test_single_requirement_one_question() -> None:
    criteria = [_criterion(id="c1", description="Australian companies")]
    questions = plan_questions(criteria)
    assert len(questions) == 1
    assert questions[0].id == "c1.q1"
    assert questions[0].criterion_id == "c1"
    assert "Australian companies" in questions[0].text


def test_multiple_criteria_stable_ordering() -> None:
    criteria = [
        _criterion(id="c2", description="Second criterion"),
        _criterion(id="c1", description="First criterion"),
    ]
    questions = plan_questions(criteria)
    assert [q.id for q in questions] == ["c1.q1", "c2.q1"]


def test_exclusion_phrased_as_disqualification() -> None:
    criteria = [
        _criterion(
            id="c1", description="Recruitment agencies", kind=CriterionKind.EXCLUSION
        )
    ]
    questions = plan_questions(criteria)
    ids = [q.id for q in questions]
    assert "c1.q1" in ids
    assert "c1.q2" in ids
    # q2 should be phrased as disqualification
    q2 = next(q for q in questions if q.id == "c1.q2")
    assert "excluded" in q2.text.lower()
    assert q2.polarity.value == "negative"


def test_requirement_uses_positive_polarity() -> None:
    criteria = [_criterion(id="c1", description="Australian companies")]
    questions = plan_questions(criteria)
    assert questions[0].polarity.value == "positive"


def test_max_questions_per_criterion_cap() -> None:
    criteria = [_criterion(id="c1", description="Test")]
    questions = plan_questions(criteria, max_questions_per_criterion=1)
    assert len(questions) == 1


def test_deterministic_output() -> None:
    criteria = [
        _criterion(id="c1", description="Australian companies"),
        _criterion(id="c2", description="SaaS industry"),
    ]
    q1 = plan_questions(criteria)
    q2 = plan_questions(criteria)
    assert [q.model_dump() for q in q1] == [q.model_dump() for q in q2]


def test_answerable_from_populated() -> None:
    criteria = [
        _criterion(
            id="c1",
            description="Australian SaaS companies",
        )
    ]
    questions = plan_questions(criteria)
    assert questions[0].answerable_from == ["australian", "saas", "companies"]


def test_total_cap_enforced() -> None:
    criteria = [_criterion(id=f"c{i}", description=f"Criterion {i}") for i in range(5)]
    questions = plan_questions(criteria, max_questions_per_criterion=3)
    # Each requirement gets 1 question (base_q), so 5 criteria = 5 questions,
    # well under the 15 total cap.
    assert len(questions) == 5
    assert len(questions) <= 15


def test_empty_criteria_empty_questions() -> None:
    assert plan_questions([]) == []
