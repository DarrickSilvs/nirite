"""Fixture recording tool — convert live model output to committed offline fixtures.

Usage: python -m nirite.eval.record --case <slug> --out evals/golden/recorded/ --live

Runs Layer 1 (and optionally Layer 3 judge answers) once against real models
and stores raw JSON with model id, prompt version, timestamp. Refuses to
overwrite without --force. Never records API keys.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from nirite.campaign.analyser import CampaignAnalyser
from nirite.campaign.llm.providers import (
    build_analysis_providers,
    build_parser_provider,
)
from nirite.campaign.parser import CampaignParser
from nirite.eval.runner import EvalFailure, assert_passing, run_definition_evals
from nirite.judge.provider import get_judge_client

REQUIRED_ENV_VARS = ("MISTRAL_OPENROUTER_API_KEY", "GEMINI_FLASH_LITE_API_KEY")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _has_api_keys() -> bool:
    import os

    return all(os.getenv(v) for v in REQUIRED_ENV_VARS)


def _record_case(
    case_slug: str,
    prompt: str,
    out_dir: Path,
    record_judge_answers: bool = False,
) -> None:
    """Run Layer 1 + optional judge answers once and record raw JSON."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{case_slug}.json"

    if out_file.exists():
        print(f"Refusing to overwrite existing fixture: {out_file}")
        print("Use --force to overwrite.")
        sys.exit(1)

    analyser = CampaignAnalyser(providers=build_analysis_providers())
    parser = CampaignParser(providers=build_parser_provider())

    # Run Layer 1
    analyses = analyser.analyse(prompt)
    definition = parser.parse(prompt, analyses)

    # Run eval gate
    report = run_definition_evals(definition, analyses[0], mode="strict")
    try:
        assert_passing(report)
    except EvalFailure as e:
        print(f"Layer 1 eval failed for case '{case_slug}':")
        for f in e.report.findings:
            if f.severity.value == "error":
                print(f"  ERROR {f.code}: {f.message}")
        sys.exit(1)

    # Record
    record = {
        "case_slug": case_slug,
        "prompt": prompt,
        "model_id": "openrouter/mistralai/ministral-3b-2512 (analysis) + gemini/gemini-3.1-flash-lite (parser)",
        "prompt_version": "1",
        "timestamp": time.time(),
        "campaign_analysis": analyses[0].model_dump(mode="json"),
        "campaign_definition": definition.model_dump(mode="json"),
        "eval_report": report.model_dump(mode="json"),
    }

    # Optionally record judge answers
    if record_judge_answers:
        judge_client = get_judge_client()
        from nirite.qualification.questions import plan_questions

        analysis = analyses[0]
        semantic_criteria = [
            c
            for c in definition.spec.criteria
            if c.evaluation_mode.value in ("semantic", "hybrid")
        ]
        analysis_semantic = [
            c
            for c in analysis.explicit_criteria
            if c.id in {sc.id for sc in semantic_criteria}
        ]
        questions = plan_questions(analysis_semantic)

        if questions:
            subject = {}
            answers = judge_client.judge(questions, subject)
            record["judge_answers"] = [a.model_dump(mode="json") for a in answers]

    tmp = out_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    tmp.replace(out_file)

    print(f"Recorded fixture: {out_file}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record live model output as offline fixtures."
    )
    parser.add_argument(
        "--case", required=True, help="Case slug (used as output filename)."
    )
    parser.add_argument(
        "--prompt", required=True, help="Natural language campaign description."
    )
    parser.add_argument(
        "--out",
        default="evals/golden/recorded",
        help="Output directory for recorded fixtures.",
    )
    parser.add_argument(
        "--record-judge-answers",
        action="store_true",
        help="Also record Layer 3 judge answers.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicit opt-in to run against real LLM APIs.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing fixture file.",
    )
    args = parser.parse_args()

    if not args.live:
        print("Refusing to run without --live flag.")
        print("This tool makes real LLM API calls. Use --live to opt in.")
        sys.exit(1)

    if not _has_api_keys():
        print(
            "Missing required API keys: MISTRAL_OPENROUTER_API_KEY, GEMINI_FLASH_LITE_API_KEY"
        )
        sys.exit(1)

    out_dir = Path(args.out)
    out_file = out_dir / f"{args.case}.json"

    if out_file.exists() and not args.force:
        print(f"Refusing to overwrite existing fixture: {out_file}")
        print("Use --force to overwrite.")
        sys.exit(1)

    _record_case(args.case, args.prompt, out_dir, args.record_judge_answers)


if __name__ == "__main__":
    main()
