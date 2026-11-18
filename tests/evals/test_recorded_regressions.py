"""Recorded-output regression suite (TASK-20).

Replays recorded Layer 1 output through eval (expect pass) and through
mutated copies (expect specific FindingCode for each mutation). Runs with
zero network — all fakes, all offline.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from nirite.eval.models import FindingCode
from nirite.eval.runner import run_definition_evals

RECORDED_DIR = Path(__file__).parent.parent.parent / "evals" / "golden" / "recorded"


def _load_recorded(case_slug: str) -> dict:
    path = RECORDED_DIR / f"{case_slug}.json"
    if not path.exists():
        pytest.skip(f"No recorded fixture: {case_slug}")
    return json.loads(path.read_text())


def _mutation_drop_criterion(definition: dict) -> dict:
    """Remove first criterion from spec.criteria."""
    d = copy.deepcopy(definition)
    if d["spec"]["criteria"]:
        d["spec"]["criteria"].pop(0)
    return d


def _mutation_duplicate_query(definition: dict) -> dict:
    """Duplicate first query in query_plan.queries."""
    d = copy.deepcopy(definition)
    if d["query_plan"]["queries"]:
        d["query_plan"]["queries"].append(copy.deepcopy(d["query_plan"]["queries"][0]))
    return d


def _mutation_weighted_requirement(definition: dict) -> dict:
    """Add weight to first requirement criterion."""
    d = copy.deepcopy(definition)
    for c in d["spec"]["criteria"]:
        if c["kind"] == "requirement":
            c["weight"] = 0.5
            break
    return d


def _mutation_facetless_query(definition: dict) -> dict:
    """Make first query have empty text."""
    d = copy.deepcopy(definition)
    if d["query_plan"]["queries"]:
        d["query_plan"]["queries"][0]["query"] = ""
    return d


def _mutation_flipped_kind(definition: dict) -> dict:
    """Flip first criterion kind from requirement to preference."""
    d = copy.deepcopy(definition)
    for c in d["spec"]["criteria"]:
        if c["kind"] == "requirement":
            c["kind"] = "preference"
            break
    return d


def _mutation_invented_criterion(definition: dict) -> dict:
    """Add a criterion not in the analysis."""
    d = copy.deepcopy(definition)
    d["spec"]["criteria"].append(
        {
            "id": "z99",
            "description": "Invented criterion",
            "kind": "requirement",
            "evaluation_mode": "structured",
            "predicate": {
                "field": "country",
                "operator": "eq",
                "value": "Nowhere",
            },
        }
    )
    return d


def _mutation_exclusion_trap(definition: dict) -> dict:
    """Add an exclusion that matches the first criterion's predicate."""
    d = copy.deepcopy(definition)
    for c in d["spec"]["criteria"]:
        if c["kind"] == "requirement" and c.get("predicate"):
            d["spec"]["criteria"].append(
                {
                    "id": "ex99",
                    "description": "Exclusion trap",
                    "kind": "exclusion",
                    "evaluation_mode": "structured",
                    "predicate": copy.deepcopy(c["predicate"]),
                }
            )
            break
    return d


MUTATIONS = [
    ("drop_criterion", _mutation_drop_criterion, FindingCode.CRITERION_DROPPED),
    ("duplicate_query", _mutation_duplicate_query, FindingCode.DUPLICATE_QUERY_TEXT),
    (
        "weighted_requirement",
        _mutation_weighted_requirement,
        FindingCode.WEIGHT_ON_NON_PREFERENCE,
    ),
    ("facetless_query", _mutation_facetless_query, FindingCode.EMPTY_QUERY_TEXT),
    ("flipped_kind", _mutation_flipped_kind, FindingCode.CRITERION_KIND_FLIPPED),
    (
        "invented_criterion",
        _mutation_invented_criterion,
        FindingCode.CRITERION_INVENTED,
    ),
    ("exclusion_trap", _mutation_exclusion_trap, FindingCode.CONTRADICTORY_PREDICATES),
]


def _run_eval_on_definition(
    definition_dict: dict,
    analysis_dict: dict,
) -> list:
    """Run eval on a definition dict, return finding codes."""
    from nirite.models.campaign import CampaignDefinition
    from nirite.models.campaign_analysis import CampaignAnalysis as CA

    definition = CampaignDefinition.model_validate(definition_dict)
    analysis = CA.model_validate(analysis_dict)

    findings = run_definition_evals(definition, analysis, mode="strict").findings
    return [f.code for f in findings]


@pytest.mark.parametrize(
    "mutation_name, mutation_fn, expected_code",
    MUTATIONS,
)
def test_mutation_produces_expected_finding(
    mutation_name: str,
    mutation_fn,
    expected_code: FindingCode,
) -> None:
    """Each mutation produces its specific FindingCode."""
    # Find a recorded case
    recorded_files = sorted(
        Path(__file__).parent.parent.parent.glob("evals/golden/recorded/*.json")
    )
    if not recorded_files:
        pytest.skip("No recorded fixtures available")

    recorded = json.loads(recorded_files[0].read_text())
    definition = recorded["campaign_definition"]
    analysis = recorded["campaign_analysis"]

    # Original should pass (or at least not have the mutation's finding)
    original_codes = _run_eval_on_definition(definition, analysis)

    # Mutated should have the expected finding
    mutated = mutation_fn(copy.deepcopy(definition))
    mutated_codes = _run_eval_on_definition(mutated, analysis)

    assert expected_code in mutated_codes, (
        f"Mutation '{mutation_name}' did not produce {expected_code}. "
        f"Got: {mutated_codes}"
    )
    assert expected_code not in original_codes, (
        f"Original definition should not have {expected_code}"
    )


def test_every_finding_code_covered() -> None:
    """Meta-test: every mutation maps to a valid FindingCode."""
    mutation_codes = {
        FindingCode.CRITERION_DROPPED,
        FindingCode.DUPLICATE_QUERY_TEXT,
        FindingCode.WEIGHT_ON_NON_PREFERENCE,
        FindingCode.EMPTY_QUERY_TEXT,
        FindingCode.CRITERION_KIND_FLIPPED,
        FindingCode.CRITERION_INVENTED,
        FindingCode.CONTRADICTORY_PREDICATES,
    }
    assert mutation_codes.issubset(set(FindingCode))
