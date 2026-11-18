"""Eval runner: aggregates deterministic checks into a strict fail-closed report.

Never calls an LLM — all checks are deterministic. In STRICT mode, any ERROR
severity finding causes ``assert_passing`` to raise ``EvalFailure``.
"""

from __future__ import annotations

from nirite.eval.checks import check_definition
from nirite.eval.consistency import check_consistency
from nirite.eval.models import EvalFinding, EvalMode, EvalReport
from nirite.models.campaign import CampaignDefinition
from nirite.models.campaign_analysis import CampaignAnalysis


class EvalFailure(RuntimeError):
    """Raised when strict eval fails — carries the full report for rendering."""

    def __init__(self, report: EvalReport) -> None:
        self.report = report
        super().__init__(
            f"Eval failed: {report.error_count} error(s), "
            f"{report.warn_count} warning(s) in {report.artifact} "
            f"(mode={report.mode.value})"
        )


def run_definition_evals(
    definition: CampaignDefinition,
    analysis: CampaignAnalysis,
    mode: EvalMode = EvalMode.STRICT,
) -> EvalReport:
    """Run all deterministic checks on a campaign definition and analysis.

    Checks run in order: structural (cheap) → consistency (more expensive).
    Never calls an LLM.
    """
    findings: list[EvalFinding] = []
    checks_run = 0

    # Phase 1: structural checks (cheap, always run)
    structural = check_definition(definition)
    findings.extend(structural)
    checks_run += 1

    # Phase 2: cross-artifact consistency (needs analysis)
    consistency = check_consistency(analysis, definition)
    findings.extend(consistency)
    checks_run += 1

    return EvalReport(
        artifact="CampaignDefinition",
        mode=mode,
        findings=findings,
        checks_run=checks_run,
    )


def assert_passing(report: EvalReport) -> None:
    """Raise ``EvalFailure`` if the report contains any ERROR findings.

    In STRICT mode, this is the hard gate. In LENIENT mode, warnings are
    allowed but errors still fail.
    """
    if not report.passed:
        raise EvalFailure(report)
