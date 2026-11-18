"""Tests for structured criterion evaluator (TASK-11)."""

from __future__ import annotations

from nirite.models.campaign import (
    Criterion,
    CriterionKind,
    EvaluationMode,
    FieldPredicate,
    PredicateField,
    PredicateOperator,
)
from nirite.models.prospect import Prospect
from nirite.qualification.structured import evaluate_structured
from tests.support.builders import build_company_prospect, build_prospect


def _criterion(
    *,
    id: str = "c1",
    kind: CriterionKind = CriterionKind.REQUIREMENT,
    field: PredicateField = PredicateField.COUNTRY,
    operator: PredicateOperator = PredicateOperator.EQ,
    value: str | None = "Australia",
    upper_value: str | None = None,
) -> Criterion:
    return Criterion(
        id=id,
        description=f"Test {id}",
        kind=kind,
        evaluation_mode=EvaluationMode.STRUCTURED,
        predicate=FieldPredicate(
            field=field,
            operator=operator,
            value=value,
            upper_value=upper_value,
        ),
    )


def test_eq_passed() -> None:
    prospect = build_prospect(country="Australia")
    criterion = _criterion(
        field=PredicateField.COUNTRY, operator=PredicateOperator.EQ, value="Australia"
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "passed"
    assert verdict.score == 1.0


def test_eq_failed() -> None:
    prospect = build_prospect(country="Germany")
    criterion = _criterion(
        field=PredicateField.COUNTRY, operator=PredicateOperator.EQ, value="Australia"
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "failed"
    assert verdict.score == 0.0


def test_missing_field_unknown() -> None:
    prospect = build_prospect(country=None)
    criterion = _criterion(
        field=PredicateField.COUNTRY, operator=PredicateOperator.EQ, value="Australia"
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "unknown"
    assert verdict.score == 0.0


def test_neq_passed() -> None:
    prospect = build_prospect(country="Germany")
    criterion = _criterion(
        field=PredicateField.COUNTRY, operator=PredicateOperator.NEQ, value="Australia"
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "passed"


def test_contains_passed() -> None:
    prospect = build_prospect(company_name="Acme SaaS Corp")
    criterion = _criterion(
        field=PredicateField.COMPANY_NAME,
        operator=PredicateOperator.CONTAINS,
        value="SaaS",
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "passed"


def test_in_passed() -> None:
    prospect = build_prospect(country="Australia")
    criterion = _criterion(
        field=PredicateField.COUNTRY,
        operator=PredicateOperator.IN,
        value=["Australia", "New Zealand"],
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "passed"


def test_exists_passed() -> None:
    prospect = build_prospect(email="jane@example.com")
    criterion = Criterion(
        id="c1",
        description="Has email",
        kind=CriterionKind.REQUIREMENT,
        evaluation_mode=EvaluationMode.STRUCTURED,
        predicate=FieldPredicate(
            field=PredicateField.EMAIL,
            operator=PredicateOperator.EXISTS,
        ),
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "passed"


def test_exists_failed_when_absent() -> None:
    prospect = build_prospect(email=None)
    criterion = Criterion(
        id="c1",
        description="Has email",
        kind=CriterionKind.REQUIREMENT,
        evaluation_mode=EvaluationMode.STRUCTURED,
        predicate=FieldPredicate(
            field=PredicateField.EMAIL,
            operator=PredicateOperator.EXISTS,
        ),
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "failed"


def test_gt_passed() -> None:
    prospect = build_company_prospect(company_size="250")
    criterion = _criterion(
        field=PredicateField.COMPANY_SIZE,
        operator=PredicateOperator.GT,
        value="100",
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "passed"


def test_gt_failed() -> None:
    prospect = build_company_prospect(company_size="50")
    criterion = _criterion(
        field=PredicateField.COMPANY_SIZE,
        operator=PredicateOperator.GT,
        value="100",
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "failed"


def test_between_passed() -> None:
    prospect = build_company_prospect(company_size="150")
    criterion = Criterion(
        id="c1",
        description="Company size between 100 and 200",
        kind=CriterionKind.REQUIREMENT,
        evaluation_mode=EvaluationMode.STRUCTURED,
        predicate=FieldPredicate(
            field=PredicateField.COMPANY_SIZE,
            operator=PredicateOperator.BETWEEN,
            value="100",
            upper_value="200",
        ),
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "passed"


def test_exclusion_match_failed() -> None:
    prospect = build_prospect(country="Australia")
    criterion = _criterion(
        id="c1",
        kind=CriterionKind.EXCLUSION,
        field=PredicateField.COUNTRY,
        operator=PredicateOperator.EQ,
        value="Australia",
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "failed"


def test_exclusion_no_match_passed() -> None:
    prospect = build_prospect(country="Germany")
    criterion = _criterion(
        id="c1",
        kind=CriterionKind.EXCLUSION,
        field=PredicateField.COUNTRY,
        operator=PredicateOperator.EQ,
        value="Australia",
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "passed"


def test_geo_expansion_country_eq() -> None:
    """country=Australia should match state=Victoria via GEO_HIERARCHY."""
    prospect = build_prospect(country=None, state="Victoria")
    criterion = _criterion(
        field=PredicateField.COUNTRY, operator=PredicateOperator.EQ, value="Australia"
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "passed"


def test_geo_expansion_country_in() -> None:
    """country IN (Australia, NZ) should match city=Melbourne via GEO_HIERARCHY."""
    prospect = build_prospect(country=None, city="Melbourne")
    criterion = _criterion(
        field=PredicateField.COUNTRY,
        operator=PredicateOperator.IN,
        value=["Australia", "New Zealand"],
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "passed"


def test_extra_fields_alias_resolution() -> None:
    """Predicate on 'city' should read 'town' from extra_fields via alias."""
    prospect = Prospect(
        full_name="Jane Doe",
        job_title="Engineer",
        company_name="Acme",
        country=None,
        extra_fields={"town": "Melbourne"},
        source_file="test.csv",
        source_row=1,
    )
    criterion = _criterion(
        field=PredicateField.CITY, operator=PredicateOperator.EQ, value="Melbourne"
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "passed"


def test_no_predicate_unknown() -> None:
    prospect = build_prospect(country="Australia")
    criterion = Criterion.model_construct(
        id="c1",
        description="No predicate",
        kind=CriterionKind.REQUIREMENT,
        evaluation_mode=EvaluationMode.STRUCTURED,
        predicate=None,
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "unknown"
    assert verdict.evidence == "no predicate"


def test_no_mutation_of_prospect() -> None:
    prospect = build_prospect(country="Australia")
    original = prospect.model_copy()
    criterion = _criterion(
        field=PredicateField.COUNTRY, operator=PredicateOperator.EQ, value="Australia"
    )
    evaluate_structured(prospect, criterion)
    assert prospect == original


def test_company_prospect_fields() -> None:
    prospect = build_company_prospect(industry="SaaS", company_size="51-200")
    criterion = _criterion(
        field=PredicateField.INDUSTRY,
        operator=PredicateOperator.EQ,
        value="SaaS",
    )
    verdict = evaluate_structured(prospect, criterion)
    assert verdict.status == "passed"
