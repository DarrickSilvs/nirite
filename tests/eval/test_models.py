"""Tests for eval artifact models (TASK-03)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nirite.eval.models import (
    EvalFinding,
    EvalMode,
    EvalReport,
    EvalSeverity,
    FindingCode,
)


def test_eval_severity_members() -> None:
    assert {s.value for s in EvalSeverity} == {"info", "warn", "error"}


def test_eval_mode_members() -> None:
    assert {m.value for m in EvalMode} == {"strict", "lenient"}


def test_finding_code_has_expected_codes() -> None:
    codes = {c.value for c in FindingCode}
    assert "schema_invalid" in codes
    assert "criterion_dropped" in codes
    assert "judge_error" in codes
    assert "quality_rubric_fail" in codes


def test_eval_finding_creation() -> None:
    finding = EvalFinding(
        check_id="check_structure",
        code=FindingCode.SCHEMA_INVALID,
        severity=EvalSeverity.ERROR,
        message="CampaignDefinition did not validate against schema",
        path="spec",
        evidence="c1",
    )
    assert finding.check_id == "check_structure"
    assert finding.code == FindingCode.SCHEMA_INVALID
    assert finding.severity == EvalSeverity.ERROR
    assert finding.path == "spec"
    assert finding.evidence == "c1"


def test_eval_report_passed_with_no_errors() -> None:
    report = EvalReport(
        artifact="CampaignDefinition",
        mode=EvalMode.STRICT,
        findings=[
            EvalFinding(
                check_id="c1",
                code=FindingCode.WEIGHT_ON_NON_PREFERENCE,
                severity=EvalSeverity.WARN,
                message="weight set on non-preference criterion",
            )
        ],
        checks_run=1,
    )
    assert report.passed is True
    assert report.error_count == 0
    assert report.warn_count == 1
    assert report.info_count == 0


def test_eval_report_failed_with_error() -> None:
    report = EvalReport(
        artifact="CampaignDefinition",
        mode=EvalMode.STRICT,
        findings=[
            EvalFinding(
                check_id="c1",
                code=FindingCode.SCHEMA_INVALID,
                severity=EvalSeverity.ERROR,
                message="schema validation failed",
            )
        ],
        checks_run=1,
    )
    assert report.passed is False
    assert report.error_count == 1


def test_eval_report_mixed_findings() -> None:
    report = EvalReport(
        artifact="CampaignDefinition",
        mode=EvalMode.LENIENT,
        findings=[
            EvalFinding(
                check_id="c1",
                code=FindingCode.SCHEMA_INVALID,
                severity=EvalSeverity.ERROR,
                message="schema invalid",
            ),
            EvalFinding(
                check_id="c2",
                code=FindingCode.DUPLICATE_QUERY_ID,
                severity=EvalSeverity.WARN,
                message="duplicate query id",
            ),
            EvalFinding(
                check_id="c3",
                code=FindingCode.EMPTY_QUERY_TEXT,
                severity=EvalSeverity.INFO,
                message="empty query",
            ),
        ],
        checks_run=3,
    )
    assert report.passed is False
    assert report.error_count == 1
    assert report.warn_count == 1
    assert report.info_count == 1


def test_eval_report_json_round_trip() -> None:
    report = EvalReport(
        artifact="CampaignDefinition",
        mode=EvalMode.STRICT,
        findings=[
            EvalFinding(
                check_id="c1",
                code=FindingCode.CRITERION_DROPPED,
                severity=EvalSeverity.ERROR,
                message="criterion c1 missing from definition",
                path="spec.criteria",
                evidence="c1",
            )
        ],
        checks_run=1,
    )
    data = report.model_dump(mode="json")
    assert data["artifact"] == "CampaignDefinition"
    assert data["mode"] == "strict"
    assert data["checks_run"] == 1
    assert len(data["findings"]) == 1
    assert data["findings"][0]["code"] == "criterion_dropped"
    # passed is a derived property, reconstruct to verify
    restored = EvalReport.model_validate(data)
    assert restored.passed is False


def test_eval_report_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EvalReport(
            artifact="x",
            mode=EvalMode.STRICT,
            unknown_field="not allowed",  # type: ignore[call-arg]
        )


def test_eval_finding_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EvalFinding(
            check_id="c1",
            code=FindingCode.SCHEMA_INVALID,
            severity=EvalSeverity.ERROR,
            message="msg",
            unknown_field="not allowed",  # type: ignore[call-arg]
        )
