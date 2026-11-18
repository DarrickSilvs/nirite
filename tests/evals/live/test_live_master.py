"""Live E2E suite (TASK-22).

Runs golden cases through the real NIM Nemotron + Gemini/Ministral stack.
Marked @pytest.mark.live — deselected by default. Run with:

    uv run pytest -m live tests/evals/live/

Requires NIM Nemotron API keys in .env.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nirite.campaign.analyser import CampaignAnalyser
from nirite.campaign.llm.providers import (
    build_analysis_providers,
    build_parser_provider,
)
from nirite.campaign.parser import CampaignParser
from nirite.eval.metrics import compute_metrics, evaluate_thresholds, load_thresholds
from nirite.eval.runner import assert_passing, run_definition_evals
from nirite.judge.provider import get_judge_client
from nirite.models.prospect import Prospect
from nirite.qualification.qualifier import qualify_from_retrieval_output
from nirite.retrieval.pipeline import run as retrieval_run

GOLDEN_DIR = (
    Path(__file__).parent.parent.parent.parent / "evals" / "golden" / "campaigns"
)


def _load_golden_case(slug: str) -> tuple[str, list[Prospect], dict[int, str]]:
    case_dir = GOLDEN_DIR / slug
    prompt = (case_dir / "prompt.txt").read_text().strip()
    candidates = json.loads((case_dir / "candidates.json").read_text())
    labels = json.loads((case_dir / "labels.json").read_text())
    prospects = [
        Prospect.model_validate({**c, "source_file": "golden.csv", "source_row": i + 2})
        for i, c in enumerate(candidates)
    ]
    return prompt, prospects, labels


@pytest.mark.live
@pytest.mark.parametrize(
    "case_slug", ["saas-australia", "saas-usa-person", "exclusion-recruitment"]
)
def test_live_master_eval(case_slug: str) -> None:
    """Run a golden case through the real LLM stack end-to-end."""
    prompt, prospects, _labels = _load_golden_case(case_slug)

    analyser = CampaignAnalyser(providers=build_analysis_providers())
    parser = CampaignParser(providers=build_parser_provider())

    analyses = analyser.analyse(prompt)
    definition = parser.parse(prompt, analyses)

    # Eval gate
    report = run_definition_evals(definition, analyses[0], mode="strict")
    assert_passing(report)

    # Layer 2 retrieval
    retrieval_output = retrieval_run(prospects, definition, top_n=20)

    # Layer 3 qualification
    judge_client = get_judge_client()
    qualification_output = qualify_from_retrieval_output(
        retrieval_output, definition, analyses[0], judge_client
    )

    # Metrics
    labels_by_rank = {v.rank - 1: v.status.value for v in qualification_output.verdicts}
    metrics = compute_metrics(qualification_output, labels_by_rank)

    # Check thresholds
    thresholds = load_thresholds()
    breaches = evaluate_thresholds(metrics, thresholds)

    assert not breaches, f"Master eval breaches: {breaches}"
