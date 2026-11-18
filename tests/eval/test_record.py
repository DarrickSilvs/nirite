"""Tests for fixture recording tool (TASK-19)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nirite.eval.record import _record_case, main


def test_record_case_writes_fixture(tmp_path) -> None:
    """Record case writes a JSON fixture with expected shape."""
    # Mock the analyser and parser to avoid real LLM calls
    mock_analysis = MagicMock()
    mock_analysis.model_dump.return_value = {"id": "c1", "description": "test"}

    mock_definition = MagicMock()
    mock_definition.model_dump.return_value = {
        "original_prompt": "test prompt",
        "spec": {"criteria": []},
        "query_plan": {"queries": []},
    }

    mock_report = MagicMock()
    mock_report.model_dump.return_value = {
        "artifact": "CampaignDefinition",
        "mode": "strict",
        "findings": [],
        "checks_run": 1,
    }
    mock_report.passed = True
    mock_report.error_count = 0

    with (
        patch("nirite.eval.record.CampaignAnalyser") as mock_analyser_cls,
        patch("nirite.eval.record.CampaignParser") as mock_parser_cls,
        patch("nirite.eval.record.run_definition_evals", return_value=mock_report),
        patch("nirite.eval.record.assert_passing"),
    ):
        mock_analyser = MagicMock()
        mock_analyser.analyse.return_value = [mock_analysis]
        mock_analyser_cls.return_value = mock_analyser

        mock_parser = MagicMock()
        mock_parser.parse.return_value = mock_definition
        mock_parser_cls.return_value = mock_parser

        out_dir = tmp_path / "recorded"
        _record_case("test-case", "test prompt", out_dir)

    out_file = out_dir / "test-case.json"
    assert out_file.exists()

    data = json.loads(out_file.read_text())
    assert data["case_slug"] == "test-case"
    assert data["prompt"] == "test prompt"
    assert "campaign_analysis" in data
    assert "campaign_definition" in data
    assert "eval_report" in data
    assert "timestamp" in data


def test_record_case_refuses_overwrite(tmp_path) -> None:
    """Record case refuses to overwrite without --force."""
    out_dir = tmp_path / "recorded"
    out_dir.mkdir()
    out_file = out_dir / "existing.json"
    out_file.write_text('{"existing": true}')

    with (
        patch("nirite.eval.record.CampaignAnalyser"),
        patch("nirite.eval.record.CampaignParser"),
        patch("nirite.eval.record.run_definition_evals"),
        patch("nirite.eval.record.assert_passing"),
        pytest.raises(SystemExit),
    ):
        _record_case("existing", "prompt", out_dir)

    # File should be unchanged
    assert json.loads(out_file.read_text()) == {"existing": True}


def test_main_requires_live_flag(monkeypatch) -> None:
    """Main refuses to run without --live flag."""
    monkeypatch.setattr("sys.argv", ["record", "--case", "test", "--prompt", "prompt"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_record_case_eval_failure_exits() -> None:
    """Record case exits on eval failure."""
    from nirite.eval.runner import EvalFailure

    mock_report = MagicMock()
    mock_report.model_dump.return_value = {
        "artifact": "CampaignDefinition",
        "mode": "strict",
        "findings": [
            {"code": "schema_invalid", "severity": "error", "message": "bad schema"}
        ],
        "checks_run": 1,
    }
    mock_report.passed = False
    mock_report.error_count = 1

    with (
        patch("nirite.eval.record.CampaignAnalyser"),
        patch("nirite.eval.record.CampaignParser"),
        patch("nirite.eval.record.run_definition_evals", return_value=mock_report),
        patch(
            "nirite.eval.record.assert_passing", side_effect=EvalFailure(mock_report)
        ),
    ):
        with pytest.raises(SystemExit) as exc_info:
            _record_case("test-case", "test prompt", Path("/tmp/test"))
        assert exc_info.value.code == 1
