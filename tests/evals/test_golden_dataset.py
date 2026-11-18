"""Tests for golden dataset validity (TASK-17).

Validates that every golden campaign directory conforms to the schema,
labels reference real candidate IDs, and each case has at least one
positive and one negative label.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).parent.parent.parent / "evals" / "golden"
CAMPAIGNS_DIR = GOLDEN_DIR / "campaigns"
SCHEMA_PATH = GOLDEN_DIR / "schema.json"


def _load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def _list_cases() -> list[Path]:
    if not CAMPAIGNS_DIR.exists():
        return []
    return sorted(d for d in CAMPAIGNS_DIR.iterdir() if d.is_dir())


def _load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _validate_against_schema(case_dir: Path, schema: dict) -> list[str]:
    """Minimal schema validation — checks required fields and types."""
    errors: list[str] = []

    prompt_path = case_dir / "prompt.txt"
    expected_path = case_dir / "expected.json"
    candidates_path = case_dir / "candidates.json"
    labels_path = case_dir / "labels.json"

    for p in (prompt_path, expected_path, candidates_path, labels_path):
        if not p.exists():
            errors.append(f"{case_dir.name}: missing {p.name}")

    if errors:
        return errors

    prompt = prompt_path.read_text().strip()
    if not prompt:
        errors.append(f"{case_dir.name}: prompt.txt is empty")

    expected = _load_json(expected_path)
    if not isinstance(expected.get("criteria_count_min"), int):
        errors.append(f"{case_dir.name}: expected.criteria_count_min missing")
    if not isinstance(expected.get("criteria_count_max"), int):
        errors.append(f"{case_dir.name}: expected.criteria_count_max missing")
    if expected.get("criteria_count_min", 0) > expected.get("criteria_count_max", 0):
        errors.append(f"{case_dir.name}: criteria_count_min > criteria_count_max")

    candidates = _load_json(candidates_path)
    if not isinstance(candidates, list) or len(candidates) < 8:
        errors.append(f"{case_dir.name}: candidates must be a list of 8+ items")

    labels = _load_json(labels_path)
    if not isinstance(labels, dict):
        errors.append(f"{case_dir.name}: labels must be an object")
    else:
        # Every label key must reference a real candidate index
        for key in labels:
            try:
                idx = int(key)
            except ValueError:
                errors.append(f"{case_dir.name}: labels key '{key}' is not an integer")
                continue
            if idx < 0 or idx >= len(candidates):
                errors.append(
                    f"{case_dir.name}: labels key '{key}' out of range (0-{len(candidates) - 1})"
                )
        # Valid labels
        for key, val in labels.items():
            if val not in ("qualified", "not_qualified", "bordered"):
                errors.append(
                    f"{case_dir.name}: labels[{key}] = '{val}' not a valid verdict"
                )
        # At least one positive and one negative
        vals = set(labels.values())
        if "qualified" not in vals:
            errors.append(f"{case_dir.name}: no qualified label")
        if "not_qualified" not in vals:
            errors.append(f"{case_dir.name}: no not_qualified label")

    return errors


@pytest.mark.parametrize("case_dir", _list_cases())
def test_golden_case_validates(case_dir: Path) -> None:
    """Every golden case directory conforms to the schema."""
    schema = _load_schema()
    errors = _validate_against_schema(case_dir, schema)
    assert not errors, "\n".join(errors)


def test_at_least_one_case() -> None:
    """There is at least one golden case."""
    cases = _list_cases()
    assert len(cases) >= 1, "No golden cases found"


def test_case_directory_structure() -> None:
    """Every campaign case directory has the expected files."""
    for case_dir in _list_cases():
        for name in ("prompt.txt", "expected.json", "candidates.json", "labels.json"):
            assert (case_dir / name).exists(), f"{case_dir.name}: missing {name}"
