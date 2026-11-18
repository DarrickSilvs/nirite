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
from nirite.eval.models import EvalMode, EvalReport, EvalSeverity
from nirite.eval.runner import EvalFailure, run_definition_evals
from nirite.models.campaign import CampaignDefinition

MAX_RE_RUNS = 1


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

    # Build a repair-enhanced prompt. Starts as the raw prompt;
    # on each EvalFailure we append the eval findings as a repair hint.
    effective_prompt = prompt
    last_report: EvalReport | None = None

    for attempt in range(MAX_RE_RUNS + 1):
        # Pass 1: Campaign Analysis
        analyses = analyser.analyse(effective_prompt)
        if not analyses:
            raise EvalFailure(
                EvalReport(
                    artifact="CampaignDefinition",
                    mode=EvalMode.STRICT,
                    findings=[
                        EvalFinding(
                            code="analysis_empty",
                            path="analyses",
                            evidence="Analyser returned zero analyses",
                            severity=EvalSeverity.ERROR,
                            message="Analyser returned zero analyses — cannot build definition.",
                        )
                    ],
                    checks_run=0,
                )
            )

        # Pass 2: Campaign Parsing
        definition = parser.parse(effective_prompt, analyses)

        # Pass 3: Strict eval gate
        report = run_definition_evals(
            definition,
            analyses[0],  # type: ignore[arg-type]
            mode=EvalMode.STRICT,
        )
        last_report = report

        if report.passed:
            return definition, report

        # Eval failed — build a repair hint and retry (if attempts remain)
        if attempt < MAX_RE_RUNS:
            repair_hint = _build_repair_hint(report)
            effective_prompt = f"""{prompt}

--- EVAL REPAIR (attempt {attempt + 1}) ---
The previous output failed evaluation. Fix these issues before regenerating:

{repair_hint}

Regenerate the campaign definition addressing every issue above."""

    # Exhausted all attempts — raise with the last report
    assert last_report is not None
    raise EvalFailure(last_report)


def _build_repair_hint(report: EvalReport) -> str:
    """Convert an EvalReport into a concise repair hint for the LLM."""
    lines: list[str] = []
    for f in report.findings:
        if f.severity == EvalSeverity.ERROR:
            lines.append(
                f"- [{f.code}] {f.message} (path: {f.path}, evidence: {f.evidence})"
            )
    return "\n".join(lines)
