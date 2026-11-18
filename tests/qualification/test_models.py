"""Tests for qualification models and verdict policy (TASK-10)."""

from __future__ import annotations

from nirite.qualification.models import (
    CandidateVerdict,
    CriterionStatus,
    CriterionVerdict,
    QualificationOutput,
    VerdictStatus,
)
from nirite.qualification.policy import aggregate_verdict, compute_preference_score


def _criterion_verdict(
    criterion_id: str,
    kind: str,
    status: CriterionStatus,
    score: float = 0.0,
) -> CriterionVerdict:
    return CriterionVerdict(
        criterion_id=criterion_id,
        kind=kind,
        mode_used="structured",
        status=status,
        score=score,
    )


def test_all_requirements_passed_qualified() -> None:
    verdicts = [
        _criterion_verdict("c1", "requirement", CriterionStatus.PASSED),
        _criterion_verdict("c2", "requirement", CriterionStatus.PASSED),
    ]
    status, reasons = aggregate_verdict(verdicts)
    assert status == VerdictStatus.QUALIFIED
    assert "no requirement criteria defined" not in reasons


def test_any_requirement_failed_not_qualified() -> None:
    verdicts = [
        _criterion_verdict("c1", "requirement", CriterionStatus.PASSED),
        _criterion_verdict("c2", "requirement", CriterionStatus.FAILED),
    ]
    status, reasons = aggregate_verdict(verdicts)
    assert status == VerdictStatus.NOT_QUALIFIED
    assert any("not met" in r for r in reasons)


def test_any_requirement_unknown_bordered() -> None:
    verdicts = [
        _criterion_verdict("c1", "requirement", CriterionStatus.PASSED),
        _criterion_verdict("c2", "requirement", CriterionStatus.UNKNOWN),
    ]
    status, reasons = aggregate_verdict(verdicts)
    assert status == VerdictStatus.BORDERED
    assert any("unknown" in r for r in reasons)


def test_any_exclusion_passed_not_qualified() -> None:
    verdicts = [
        _criterion_verdict("c1", "requirement", CriterionStatus.PASSED),
        _criterion_verdict("c2", "exclusion", CriterionStatus.PASSED),
    ]
    status, reasons = aggregate_verdict(verdicts)
    assert status == VerdictStatus.NOT_QUALIFIED
    assert any("exclusion" in r for r in reasons)


def test_exclusion_failed_does_not_disqualify() -> None:
    verdicts = [
        _criterion_verdict("c1", "requirement", CriterionStatus.PASSED),
        _criterion_verdict("c2", "exclusion", CriterionStatus.FAILED),
    ]
    status, _reasons = aggregate_verdict(verdicts)
    assert status == VerdictStatus.QUALIFIED


def test_exclusion_unknown_does_not_disqualify() -> None:
    verdicts = [
        _criterion_verdict("c1", "requirement", CriterionStatus.PASSED),
        _criterion_verdict("c2", "exclusion", CriterionStatus.UNKNOWN),
    ]
    status, _reasons = aggregate_verdict(verdicts)
    assert status == VerdictStatus.QUALIFIED


def test_only_preferences_bordered() -> None:
    verdicts = [
        _criterion_verdict("c1", "preference", CriterionStatus.PASSED, score=0.8),
    ]
    status, _reasons = aggregate_verdict(verdicts)
    assert status == VerdictStatus.BORDERED


def test_empty_criteria_bordered() -> None:
    status, reasons = aggregate_verdict([])
    assert status == VerdictStatus.BORDERED
    assert "no criteria" in reasons[0]


def test_no_requirements_bordered() -> None:
    verdicts = [
        _criterion_verdict("c1", "exclusion", CriterionStatus.FAILED),
    ]
    status, reasons = aggregate_verdict(verdicts)
    assert status == VerdictStatus.BORDERED
    assert any("no requirement" in r for r in reasons)


def test_compute_preference_score() -> None:
    verdicts = [
        _criterion_verdict("p1", "preference", CriterionStatus.PASSED, score=1.0),
        _criterion_verdict("p2", "preference", CriterionStatus.PASSED, score=0.5),
        _criterion_verdict("r1", "requirement", CriterionStatus.PASSED),
    ]
    assert compute_preference_score(verdicts) == 0.75


def test_compute_preference_score_no_preferences() -> None:
    verdicts = [_criterion_verdict("r1", "requirement", CriterionStatus.PASSED)]
    assert compute_preference_score(verdicts) == 0.0


def test_criterion_verdict_model() -> None:
    cv = CriterionVerdict(
        criterion_id="c1",
        kind="requirement",
        mode_used="structured",
        status=CriterionStatus.PASSED,
        score=1.0,
        evidence="country=Australia",
        judge_answer_ids=["q1"],
    )
    assert cv.criterion_id == "c1"
    assert cv.score == 1.0
    assert cv.judge_answer_ids == ["q1"]


def test_candidate_verdict_model() -> None:
    cv = CandidateVerdict(
        rank=1,
        prospect_hash="abc123",
        prospect_label="Jane Doe",
        status=VerdictStatus.QUALIFIED,
        criterion_verdicts=[
            CriterionVerdict(
                criterion_id="c1",
                kind="requirement",
                mode_used="structured",
                status=CriterionStatus.PASSED,
            )
        ],
        preference_score=0.8,
        reasons=["all requirements met"],
    )
    assert cv.status == VerdictStatus.QUALIFIED
    assert cv.preference_score == 0.8


def test_qualification_output_counts_match() -> None:
    output = QualificationOutput(
        campaign_hash="camp123",
        judge_model="openrouter/mistralai/ministral-3b-2512",
        prompt_version="1",
        verdicts=[
            CandidateVerdict(
                rank=1,
                prospect_hash="h1",
                prospect_label="Prospect A",
                status=VerdictStatus.QUALIFIED,
                criterion_verdicts=[
                    CriterionVerdict(
                        criterion_id="c1",
                        kind="requirement",
                        mode_used="structured",
                        status=CriterionStatus.PASSED,
                    )
                ],
            ),
            CandidateVerdict(
                rank=2,
                prospect_hash="h2",
                prospect_label="Prospect B",
                status=VerdictStatus.NOT_QUALIFIED,
                criterion_verdicts=[
                    CriterionVerdict(
                        criterion_id="c1",
                        kind="requirement",
                        mode_used="structured",
                        status=CriterionStatus.FAILED,
                    )
                ],
            ),
            CandidateVerdict(
                rank=3,
                prospect_hash="h3",
                prospect_label="Prospect C",
                status=VerdictStatus.BORDERED,
                criterion_verdicts=[
                    CriterionVerdict(
                        criterion_id="c1",
                        kind="requirement",
                        mode_used="structured",
                        status=CriterionStatus.UNKNOWN,
                    )
                ],
            ),
        ],
        counts={"qualified": 1, "not_qualified": 1, "bordered": 1},
    )
    assert output.qualified_count == 1
    assert output.not_qualified_count == 1
    assert output.bordered_count == 1
    assert len(output.verdicts) == 3


def test_qualification_output_counts_mismatch_raises() -> None:
    try:
        QualificationOutput(
            campaign_hash="camp123",
            judge_model="test",
            prompt_version="1",
            verdicts=[
                CandidateVerdict(
                    rank=1,
                    prospect_hash="h1",
                    prospect_label="A",
                    status=VerdictStatus.QUALIFIED,
                    criterion_verdicts=[
                        CriterionVerdict(
                            criterion_id="c1",
                            kind="requirement",
                            mode_used="structured",
                            status=CriterionStatus.PASSED,
                        )
                    ],
                )
            ],
            counts={"qualified": 0},  # wrong count
        )
    except ValueError:
        pass
    else:
        raise AssertionError("count mismatch should raise ValueError")


def test_duplicate_criterion_ids_rejected() -> None:
    try:
        CandidateVerdict(
            rank=1,
            prospect_hash="h1",
            prospect_label="A",
            status=VerdictStatus.QUALIFIED,
            criterion_verdicts=[
                CriterionVerdict(
                    criterion_id="c1",
                    kind="requirement",
                    mode_used="structured",
                    status=CriterionStatus.PASSED,
                ),
                CriterionVerdict(
                    criterion_id="c1",
                    kind="requirement",
                    mode_used="structured",
                    status=CriterionStatus.PASSED,
                ),
            ],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate criterion IDs should raise ValueError")
