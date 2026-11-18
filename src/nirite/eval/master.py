"""Master eval orchestrator — L1→L2→L3→metrics with bounded re-run.

End-to-end evaluation: build definition (eval-gated) → retrieve → qualify
→ metrics → compare thresholds. On threshold breach, re-run Layer 1 **once**
with a repair hint built from failing findings. Second breach → fail with
report. Artifacts written to evals/results/<date>-<case>/.

Hard cap of 1 re-run (explicit constant, tested).
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nirite.campaign.analyser import CampaignAnalyser
from nirite.campaign.llm.providers import (
    build_analysis_providers,
    build_parser_provider,
)
from nirite.campaign.parser import CampaignParser
from nirite.eval.metrics import compute_metrics, evaluate_thresholds, load_thresholds
from nirite.eval.models import EvalFinding, EvalSeverity
from nirite.eval.runner import EvalFailure, assert_passing, run_definition_evals
from nirite.judge.client import JudgeClient
from nirite.models.campaign import CampaignDefinition
from nirite.models.company import CompanyProspect
from nirite.models.prospect import Prospect
from nirite.qualification.qualifier import qualify_from_retrieval_output
from nirite.retrieval.pipeline import run as retrieval_run

MAX_RE_RUNS = 1


class MasterReport:
    """Result of a master eval run."""

    def __init__(
        self,
        case_name: str,
        attempt_count: int,
        stage_timings: dict[str, float],
        breaches: list[dict],
        final_definition_hash: str,
        repair_definition_hash: str | None,
        passed: bool,
        output_path: Path | None = None,
    ) -> None:
        self.case_name = case_name
        self.attempt_count = attempt_count
        self.stage_timings = stage_timings
        self.breaches = breaches
        self.final_definition_hash = final_definition_hash
        self.repair_definition_hash = repair_definition_hash
        self.passed = passed
        self.output_path = output_path

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_name": self.case_name,
            "attempt_count": self.attempt_count,
            "stage_timings": self.stage_timings,
            "breaches": self.breaches,
            "final_definition_hash": self.final_definition_hash,
            "repair_definition_hash": self.repair_definition_hash,
            "passed": self.passed,
            "output_path": str(self.output_path) if self.output_path else None,
        }


def _hash_definition(definition: CampaignDefinition) -> str:
    return hashlib.sha256(
        json.dumps(definition.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()[:16]


def _build_repair_hint(findings: list[EvalFinding]) -> str:
    """Build a repair hint from eval findings for Layer 1 re-run."""
    hints: list[str] = []
    for f in findings:
        if f.severity == EvalSeverity.ERROR:
            hints.append(f"{f.code}: {f.message}")
    if not hints:
        return "Please review and improve the campaign definition."
    return "Fix the following issues: " + "; ".join(hints)


def run_master_eval(
    case_name: str,
    prompt: str,
    prospects: list[Prospect | CompanyProspect],
    judge_client: JudgeClient,
    output_dir: Path | None = None,
) -> MasterReport:
    """Run master eval: L1→L2→L3→metrics with one bounded re-run on breach.

    Returns a MasterReport. Artifacts written to output_dir if provided.
    """
    start = time.time()
    stage_timings: dict[str, float] = {}

    attempt_count = 0
    repair_hint: str | None = None
    repair_definition_hash: str | None = None

    for attempt in range(MAX_RE_RUNS + 1):
        attempt_count = attempt + 1

        # Layer 1: build campaign definition (eval-gated)
        t0 = time.time()
        analyser = CampaignAnalyser(providers=build_analysis_providers())
        parser = CampaignParser(providers=build_parser_provider())

        if repair_hint:
            augmented_prompt = f"{prompt}\n\nRepair hint: {repair_hint}"
        else:
            augmented_prompt = prompt

        analyses = analyser.analyse(augmented_prompt)
        definition = parser.parse(augmented_prompt, analyses)

        # Eval gate
        try:
            report = run_definition_evals(definition, analyses[0], mode="strict")
            assert_passing(report)
        except EvalFailure as eval_failure:
            # Treat eval failure as a breach
            breach_dicts = [
                {
                    "metric": f.code,
                    "actual": 0.0,
                    "threshold": 1.0,
                    "direction": "gte",
                }
                for f in eval_failure.report.findings
                if f.severity == EvalSeverity.ERROR
            ]
            if attempt < MAX_RE_RUNS:
                repair_hint = _build_repair_hint(eval_failure.report.findings)
                repair_definition_hash = _hash_definition(definition)
                stage_timings["breach"] = time.time() - start
                continue
            # Second eval failure — fail
            return MasterReport(
                case_name=case_name,
                attempt_count=attempt_count,
                stage_timings=stage_timings,
                breaches=breach_dicts,
                final_definition_hash=_hash_definition(definition),
                repair_definition_hash=repair_definition_hash,
                passed=False,
                output_path=None,
            )

        # Layer 2: retrieval
        t0 = time.time()
        retrieval_output = retrieval_run(prospects, definition, top_n=20)
        stage_timings["layer2"] = time.time() - t0

        # Layer 3: qualification
        t0 = time.time()
        qualification_output = qualify_from_retrieval_output(
            retrieval_output, definition, analyses[0], judge_client
        )
        stage_timings["layer3"] = time.time() - t0

        # Metrics
        t0 = time.time()
        labels: dict[int, str] = {}
        for v in qualification_output.verdicts:
            labels[v.rank - 1] = v.status.value

        metrics = compute_metrics(qualification_output, labels)
        stage_timings["metrics"] = time.time() - t0

        # Check thresholds
        thresholds = load_thresholds()
        breaches = evaluate_thresholds(metrics, thresholds)

        if not breaches:
            # Passed
            final_hash = _hash_definition(definition)
            output_path = None
            if output_dir:
                output_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
                output_path = output_dir / f"{ts}-{case_name}.json"
                output_path.write_text(
                    json.dumps(
                        {
                            "case_name": case_name,
                            "attempt_count": attempt_count,
                            "stage_timings": stage_timings,
                            "breaches": [],
                            "metrics": metrics,
                            "final_definition_hash": final_hash,
                            "repaired": False,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )

            return MasterReport(
                case_name=case_name,
                attempt_count=attempt_count,
                stage_timings=stage_timings,
                breaches=[],
                final_definition_hash=final_hash,
                repair_definition_hash=None,
                passed=True,
                output_path=output_path,
            )

        # Breach — build repair hint and retry (if not last attempt)
        breach_dicts = [
            {
                "metric": b.metric,
                "actual": b.actual,
                "threshold": b.threshold,
                "direction": b.direction,
            }
            for b in breaches
        ]

        if attempt < MAX_RE_RUNS:
            repair_hint = _build_repair_hint(report.findings)
            repair_definition_hash = _hash_definition(definition)
            stage_timings["breach"] = time.time() - start
            continue

        # Second breach — fail
        final_hash = _hash_definition(definition)
        output_path = None
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
            output_path = output_dir / f"{ts}-{case_name}.json"
            output_path.write_text(
                json.dumps(
                    {
                        "case_name": case_name,
                        "attempt_count": attempt_count,
                        "stage_timings": stage_timings,
                        "breaches": breach_dicts,
                        "metrics": metrics,
                        "final_definition_hash": final_hash,
                        "repaired": False,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        return MasterReport(
            case_name=case_name,
            attempt_count=attempt_count,
            stage_timings=stage_timings,
            breaches=breach_dicts,
            final_definition_hash=final_hash,
            repair_definition_hash=repair_definition_hash,
            passed=False,
            output_path=output_path,
        )

    # Should not reach here
    return MasterReport(
        case_name=case_name,
        attempt_count=attempt_count,
        stage_timings=stage_timings,
        breaches=[],
        final_definition_hash="",
        repair_definition_hash=None,
        passed=False,
        output_path=None,
    )
