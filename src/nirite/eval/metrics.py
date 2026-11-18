"""Master eval metrics — precision/recall@K and verdict confusion.

Computes precision@K, recall@K, and verdict confusion from Layer 3
qualification output compared against golden labels. Thresholds are loaded
from evals/golden/thresholds.json with documented defaults.
"""

from __future__ import annotations

import json
from pathlib import Path

from nirite.qualification.models import (
    CandidateVerdict,
    QualificationOutput,
    VerdictStatus,
)

DEFAULT_THRESHOLDS = {
    "precision_at_10": 0.7,
    "recall_at_20": 0.8,
}


class ThresholdBreach:
    """A threshold breach detected by the master eval."""

    def __init__(
        self,
        metric: str,
        actual: float,
        threshold: float,
        direction: str,
    ) -> None:
        self.metric = metric
        self.actual = actual
        self.threshold = threshold
        self.direction = direction  # "gte" or "lte"

    def __repr__(self) -> str:
        return f"ThresholdBreach({self.metric}={self.actual:.3f}, threshold={self.threshold})"


def precision_at_k(
    verdicts: list[CandidateVerdict],
    labels: dict[int, str],
    k: int,
) -> float:
    """Precision@K: share of top-K predicted-qualified that are actually qualified.

    BORDERED counts as neither positive nor negative for precision.
    """
    if k <= 0 or not verdicts:
        return 0.0

    top_k = verdicts[:k]
    true_positives = 0
    predicted_positives = 0

    for verdict in top_k:
        idx = verdict.rank - 1  # rank is 1-based
        if idx < 0 or idx >= len(labels):
            continue
        label = labels.get(idx)
        if label is None:
            continue

        if verdict.status == VerdictStatus.QUALIFIED:
            predicted_positives += 1
            if label == "qualified":
                true_positives += 1

    if predicted_positives == 0:
        return 0.0
    return true_positives / predicted_positives


def recall_at_k(
    verdicts: list[CandidateVerdict],
    labels: dict[int, str],
    k: int,
) -> float:
    """Recall@K: share of actually-qualified that are predicted qualified in top-K.

    BORDERED counts as a recall-miss (not retrieved as qualified).
    """
    if k <= 0 or not verdicts:
        return 0.0

    top_k = verdicts[:k]
    top_k_qualified_ids = {
        v.rank - 1
        for v in top_k
        if v.status == VerdictStatus.QUALIFIED and 0 <= v.rank - 1 < len(labels)
    }

    total_qualified = sum(1 for label in labels.values() if label == "qualified")
    if total_qualified == 0:
        return 0.0

    retrieved_qualified = len(top_k_qualified_ids)
    return retrieved_qualified / total_qualified


def verdict_confusion(
    verdicts: list[CandidateVerdict],
    labels: dict[int, str],
) -> dict[str, int]:
    """Confusion matrix: {true_positives, false_positives, false_negatives, true_negatives}.

    BORDERED counts as neither positive nor negative.
    """
    tp = fp = fn = tn = 0

    for verdict in verdicts:
        idx = verdict.rank - 1
        if idx < 0 or idx >= len(labels):
            continue
        label = labels.get(idx)
        if label is None:
            continue

        predicted = verdict.status == VerdictStatus.QUALIFIED
        actual = label == "qualified"

        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1
        else:
            tn += 1

    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
    }


def evaluate_thresholds(
    metrics: dict[str, float],
    thresholds: dict[str, float] | None = None,
) -> list[ThresholdBreach]:
    """Compare metrics against thresholds, returning breaches.

    thresholds: dict of metric_name -> threshold value.
    Direction: "gte" means metric must be >= threshold (precision, recall).
    """
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS

    breaches: list[ThresholdBreach] = []
    for metric, threshold in thresholds.items():
        actual = metrics.get(metric, 0.0)
        if actual < threshold:
            breaches.append(
                ThresholdBreach(
                    metric=metric,
                    actual=actual,
                    threshold=threshold,
                    direction="gte",
                )
            )
    return breaches


def load_thresholds(path: Path | str | None = None) -> dict[str, float]:
    """Load thresholds from evals/golden/thresholds.json with defaults."""
    if path is None:
        path = (
            Path(__file__).resolve().parent.parent.parent
            / "evals"
            / "golden"
            / "thresholds.json"
        )

    if Path(path).exists():
        with open(path) as f:
            return json.load(f)
    return dict(DEFAULT_THRESHOLDS)


def compute_metrics(
    output: QualificationOutput,
    labels: dict[int, str],
    k_values: list[int] | None = None,
) -> dict[str, float]:
    """Compute all metrics from a QualificationOutput and labels."""
    if k_values is None:
        k_values = [10, 20]

    metrics: dict[str, float] = {}

    for k in k_values:
        metrics[f"precision@{k}"] = precision_at_k(output.verdicts, labels, k)
        metrics[f"recall@{k}"] = recall_at_k(output.verdicts, labels, k)

    confusion = verdict_confusion(output.verdicts, labels)
    metrics.update(
        {
            "true_positives": float(confusion["true_positives"]),
            "false_positives": float(confusion["false_positives"]),
            "false_negatives": float(confusion["false_negatives"]),
            "true_negatives": float(confusion["true_negatives"]),
        }
    )

    return metrics
