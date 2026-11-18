"""Campaign build service — Layer 1 with strict eval gate.

Wraps CampaignAnalyser + CampaignParser + eval runner into a single
fail-closed entry point. Returns (definition, report) on success;
raises EvalFailure on strict eval failure (no output written).
"""

from __future__ import annotations

from nirite.campaign.analyser import CampaignAnalyser
from nirite.campaign.llm.providers import (
    build_analysis_providers,
    build_parser_provider,
)
from nirite.campaign.parser import CampaignParser
from nirite.eval.models import EvalReport
from nirite.eval.runner import assert_passing, run_definition_evals
from nirite.models.campaign import CampaignDefinition


def build_campaign_definition(
    prompt: str,
    *,
    analyser: CampaignAnalyser | None = None,
    parser: CampaignParser | None = None,
) -> tuple[CampaignDefinition, EvalReport]:
    """Build a CampaignDefinition from a natural-language prompt.

    Runs Layer 1 (analysis + parse) then strict eval. On eval failure,
    raises EvalFailure — no output file should be written by the caller.

    Returns (definition, report) on success.
    """
    if analyser is None:
        analyser = CampaignAnalyser(providers=build_analysis_providers())
    if parser is None:
        parser = CampaignParser(providers=build_parser_provider())

    # Pass 1: Campaign Analysis
    analyses = analyser.analyse(prompt)

    # Pass 2: Campaign Parsing
    definition = parser.parse(prompt, analyses)

    # Pass 3: Strict eval gate
    report = run_definition_evals(
        definition, analyses[0] if analyses else None, mode="strict"
    )  # type: ignore[arg-type]
    assert_passing(report)

    return definition, report
