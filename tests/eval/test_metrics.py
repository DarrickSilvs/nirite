"""Tests for metrics module (TASK-18)."""

from __future__ import annotations

from pathlib import Path

from nirite.eval.metrics import (
    DEFAULT_THRESHOLDS,
    ThresholdBreach,
    compute_metrics,
    evaluate_thresholds,
    load_thresholds,
    precision_at_k,
    recall_at_k,
    verdict_confusion,
)
from nirite.qualification.models import (
    CandidateVerdict,
    CriterionStatus,
    CriterionVerdict,
    QualificationOutput,
    VerdictStatus,
)


def _make_verdict(
    rank: int,
    status: VerdictStatus,
    prospect_hash: str = "h",
    prospect_label: str = "p",
) -> CandidateVerdict:
    return CandidateVerdict(
        rank=rank,
        prospect_hash=f"{prospect_hash}{rank}",
        prospect_label=f"{prospect_label}{rank}",
        status=status,
        criterion_verdicts=[
            CriterionVerdict(
                criterion_id="c1",
                kind="requirement",
                mode_used="structured",
                status=CriterionStatus.PASSED,
            )
        ],
    )


def test_precision_at_k_all_correct() -> None:
    verdicts = [
        _make_verdict(1, VerdictStatus.QUALIFIED),
        _make_verdict(2, VerdictStatus.QUALIFIED),
        _make_verdict(3, VerdictStatus.NOT_QUALIFIED),
    ]
    labels = {0: "qualified", 1: "qualified", 2: "not_qualified"}
    assert precision_at_k(verdicts, labels, 2) == 1.0
    assert precision_at_k(verdicts, labels, 3) == 1.0


def test_precision_at_k_bordered_not_predicted() -> None:
    verdicts = [
        _make_verdict(1, VerdictStatus.QUALIFIED),
        _make_verdict(2, VerdictStatus.BORDERED),
    ]
    labels = {0: "qualified", 1: "qualified"}
    # BORDERED is not predicted positive, so precision = 1/1 = 1.0
    assert precision_at_k(verdicts, labels, 2) == 1.0


def test_precision_at_k_empty() -> None:
    assert precision_at_k([], {}, 10) == 0.0
    assert precision_at_k([], {}, 0) == 0.0


def test_recall_at_k_all_retrieved() -> None:
    verdicts = [
        _make_verdict(1, VerdictStatus.QUALIFIED),
        _make_verdict(2, VerdictStatus.QUALIFIED),
        _make_verdict(3, VerdictStatus.NOT_QUALIFIED),
    ]
    labels = {0: "qualified", 1: "qualified", 2: "not_qualified"}
    assert recall_at_k(verdicts, labels, 2) == 1.0
    assert recall_at_k(verdicts, labels, 3) == 1.0


def test_recall_at_k_missed() -> None:
    verdicts = [
        _make_verdict(1, VerdictStatus.NOT_QUALIFIED),
        _make_verdict(2, VerdictStatus.QUALIFIED),
    ]
    labels = {0: "qualified", 1: "qualified"}
    # Only 1 of 2 qualified retrieved → recall = 0.5
    assert recall_at_k(verdicts, labels, 2) == 0.5


def test_recall_at_k_bordered_is_miss() -> None:
    verdicts = [
        _make_verdict(1, VerdictStatus.BORDERED),
        _make_verdict(2, VerdictStatus.QUALIFIED),
    ]
    labels = {0: "qualified", 1: "qualified"}
    # BORDERED counts as recall-miss → 1/2 = 0.5
    assert recall_at_k(verdicts, labels, 2) == 0.5


def test_verdict_confusion() -> None:
    verdicts = [
        _make_verdict(1, VerdictStatus.QUALIFIED),  # TP
        _make_verdict(2, VerdictStatus.QUALIFIED),  # FP (actual not_qualified)
        _make_verdict(3, VerdictStatus.NOT_QUALIFIED),  # FN (actual qualified)
        _make_verdict(4, VerdictStatus.NOT_QUALIFIED),  # TN
    ]
    labels = {
        0: "qualified",
        1: "not_qualified",
        2: "qualified",
        3: "not_qualified",
    }
    confusion = verdict_confusion(verdicts, labels)
    assert confusion["true_positives"] == 1
    assert confusion["false_positives"] == 1
    assert confusion["false_negatives"] == 1
    assert confusion["true_negatives"] == 1


def test_evaluate_thresholds_breach() -> None:
    metrics = {"precision_at_10": 0.5, "recall_at_20": 0.9}
    breaches = evaluate_thresholds(metrics)
    assert len(breaches) == 1
    assert breaches[0].metric == "precision_at_10"
    assert breaches[0].actual == 0.5
    assert breaches[0].threshold == 0.7


def test_evaluate_thresholds_no_breach() -> None:
    metrics = {"precision_at_10": 0.8, "recall_at_20": 0.9}
    breaches = evaluate_thresholds(metrics)
    assert breaches == []


def test_default_thresholds() -> None:
    assert DEFAULT_THRESHOLDS["precision_at_10"] == 0.7
    assert DEFAULT_THRESHOLDS["recall_at_20"] == 0.8


def test_compute_metrics() -> None:
    verdicts = [
        _make_verdict(1, VerdictStatus.QUALIFIED),
        _make_verdict(2, VerdictStatus.NOT_QUALIFIED),
    ]
    labels = {0: "qualified", 1: "not_qualified"}
    output = QualificationOutput(
        campaign_hash="c1",
        judge_model="test",
        prompt_version="1",
        verdicts=verdicts,
        counts={"qualified": 1, "not_qualified": 1, "bordered": 0},
    )
    metrics = compute_metrics(output, labels, k_values=[1, 2])
    assert metrics["precision@1"] == 1.0
    assert metrics["precision@2"] == 1.0
    assert metrics["recall@1"] == 1.0
    assert metrics["recall@2"] == 1.0


def test_load_thresholds_defaults() -> None:
    thresholds = load_thresholds(Path("/nonexistent/path.json"))
    assert thresholds == DEFAULT_THRESHOLDS


def test_threshold_breach_repr() -> None:
    b = ThresholdBreach("precision_at_10", 0.5, 0.7, "gte")
    assert "precision_at_10" in repr(b)
    assert "0.5" in repr(b)
