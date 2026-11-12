"""Tests for Tier 1 deterministic filter."""

import pytest

from nirite.models.campaign import (
    Criterion,
    CriterionKind,
    EvaluationMode,
    FieldPredicate,
    PredicateField,
    PredicateOperator,
    TargetType,
)
from nirite.models.company import CompanyProspect
from nirite.models.prospect import Prospect

from nirite.retrieval.tier1_filter import _expand_geo_predicate, tier1_filter


@pytest.fixture
def individual_prospects():
    return [
        Prospect(
            full_name="John Smith",
            first_name="John",
            last_name="Smith",
            job_title="Software Engineer",
            company_name="Acme Corp",
            company_domain="acme.com",
            company_website="https://acme.com",
            email="john@acme.com",
            city="Sydney",
            state="NSW",
            country="Australia",
            source_file="leads.csv",
            source_row=2,
        ),
        Prospect(
            full_name="Jane Doe",
            first_name="Jane",
            last_name="Doe",
            job_title="Marketing Manager",
            company_name="Globex",
            company_domain="globex.com",
            company_website="https://globex.com",
            email="jane@globex.com",
            city="Melbourne",
            state="VIC",
            country="Australia",
            source_file="leads.csv",
            source_row=3,
        ),
        Prospect(
            full_name="Bob Wilson",
            first_name="Bob",
            last_name="Wilson",
            job_title="Sales Rep",
            company_name="TestCo",
            company_domain="testco.com",
            company_website="https://testco.com",
            email="bob@testco.com",
            city="Brisbane",
            state="QLD",
            country="Australia",
            source_file="leads.csv",
            source_row=4,
        ),
    ]


@pytest.fixture
def company_prospects():
    return [
        CompanyProspect(
            company_name="Acme Corp",
            company_domain="acme.com",
            company_website="https://acme.com",
            industry="SaaS",
            company_size="51-200",
            city="Sydney",
            country="Australia",
            linkedin_url="https://linkedin.com/company/acme",
            description="B2B SaaS platform for logistics automation.",
            source_file="companies.csv",
            source_row=2,
        ),
        CompanyProspect(
            company_name="Globex",
            company_domain="globex.com",
            company_website="https://globex.com",
            industry="Marketing",
            company_size="11-50",
            city="Melbourne",
            country="Australia",
            linkedin_url=None,
            description="Full-service marketing agency.",
            source_file="companies.csv",
            source_row=3,
        ),
        CompanyProspect(
            company_name="TestCo",
            company_domain="testco.com",
            company_website="https://testco.com",
            industry="Retail",
            company_size="1-10",
            region="EMEA",
            city="Brisbane",
            country="Australia",
            linkedin_url="https://linkedin.com/company/testco",
            description=None,
            source_file="companies.csv",
            source_row=4,
        ),
    ]


def _requirement_predicate(field, operator, value):
    return FieldPredicate(
        field=field,
        operator=operator,
        value=value,
    )


def _exclusion_predicate(field, operator, value):
    return FieldPredicate(
        field=field,
        operator=operator,
        value=value,
    )


def _spec(criteria):
    return type(
        "Spec",
        (),
        {"criteria": criteria},
    )()


def test_tier1_filter_keeps_prospects_matching_all_requirements(individual_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Must be in Australia",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.COUNTRY, PredicateOperator.EQ, "Australia"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(individual_prospects, spec)
    assert len(result) == 3


def test_tier1_filter_excludes_prospects_not_matching_requirement(individual_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Must be in Sydney",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.CITY, PredicateOperator.EQ, "Sydney"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(individual_prospects, spec)
    assert len(result) == 1
    assert result[0].full_name == "John Smith"


def test_tier1_filter_removes_excluded_prospects(individual_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Must be in Australia",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.COUNTRY, PredicateOperator.EQ, "Australia"),
        ),
        Criterion(
            id="c2",
            description="Exclude Brisbane",
            kind=CriterionKind.EXCLUSION,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_exclusion_predicate(PredicateField.CITY, PredicateOperator.EQ, "Brisbane"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(individual_prospects, spec)
    assert len(result) == 2
    cities = {p.city for p in result}
    assert cities == {"Sydney", "Melbourne"}


def test_tier1_filter_contains_operator(individual_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Company name contains Acme",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.COMPANY_NAME, PredicateOperator.CONTAINS, "acme"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(individual_prospects, spec)
    assert len(result) == 1
    assert result[0].company_name == "Acme Corp"


def test_tier1_filter_in_operator(individual_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="City in Sydney or Melbourne",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.CITY, PredicateOperator.IN, ["Sydney", "Melbourne"]),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(individual_prospects, spec)
    assert len(result) == 2


def test_tier1_filter_exists_operator(individual_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Must have email",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.EMAIL, PredicateOperator.EXISTS, None),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(individual_prospects, spec)
    assert len(result) == 3  # all have email


def test_tier1_filter_exclusion_exists(individual_prospects):
    # Bob has no profile_url
    prospects = [
        Prospect(
            full_name="John Smith",
            first_name="John",
            last_name="Smith",
            job_title="Engineer",
            company_name="Acme",
            profile_url="https://linkedin.com/in/john",
            source_file="f.csv",
            source_row=1,
        ),
        Prospect(
            full_name="Jane Doe",
            first_name="Jane",
            last_name="Doe",
            job_title="Manager",
            company_name="Globex",
            profile_url=None,
            source_file="f.csv",
            source_row=2,
        ),
    ]
    criteria = [
        Criterion(
            id="c1",
            description="Must NOT have profile_url",
            kind=CriterionKind.EXCLUSION,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_exclusion_predicate(PredicateField.PROFILE_URL, PredicateOperator.EXISTS, None),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(prospects, spec)
    assert len(result) == 1
    assert result[0].full_name == "Jane Doe"


def test_tier1_filter_returns_empty_when_no_match(individual_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Must be in London",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.CITY, PredicateOperator.EQ, "London"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(individual_prospects, spec)
    assert result == []


def test_tier1_filter_ignores_semantic_criteria(individual_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Company is innovative",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.SEMANTIC,
            predicate=None,
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(individual_prospects, spec)
    assert len(result) == 3  # semantic criteria not applied in Tier 1


def test_tier1_filter_ignores_preferences(individual_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Prefer Sydney",
            kind=CriterionKind.PREFERENCE,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.CITY, PredicateOperator.EQ, "Sydney"),
            weight=0.8,
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(individual_prospects, spec)
    assert len(result) == 3  # preferences not applied in Tier 1


def test_tier1_filter_no_criteria_keeps_all(individual_prospects):
    spec = _spec([])
    result = tier1_filter(individual_prospects, spec)
    assert len(result) == 3


def test_tier1_filter_does_not_mutate_input(individual_prospects):
    original_count = len(individual_prospects)
    criteria = [
        Criterion(
            id="c1",
            description="Must be in Sydney",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.CITY, PredicateOperator.EQ, "Sydney"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(individual_prospects, spec)
    assert len(individual_prospects) == original_count  # input unchanged
    assert len(result) == 1


def test_tier1_filter_with_company_prospects(company_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Must be in Australia",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.COUNTRY, PredicateOperator.EQ, "Australia"),
        ),
        Criterion(
            id="c2",
            description="Exclude Retail",
            kind=CriterionKind.EXCLUSION,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_exclusion_predicate(PredicateField.COMPANY_NAME, PredicateOperator.EQ, "TestCo"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(company_prospects, spec)
    assert len(result) == 2
    names = {c.company_name for c in result}
    assert names == {"Acme Corp", "Globex"}


def test_tier1_filter_company_eq_industry(company_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Industry is SaaS",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(
                PredicateField.INDUSTRY, PredicateOperator.EQ, "SaaS"
            ),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(company_prospects, spec)
    assert len(result) == 1
    assert result[0].company_name == "Acme Corp"


def test_tier1_filter_company_contains_description(company_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Description contains automation",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(
                PredicateField.DESCRIPTION,
                PredicateOperator.CONTAINS,
                "automation",
            ),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(company_prospects, spec)
    assert len(result) == 1
    assert result[0].company_name == "Acme Corp"


def test_tier1_filter_company_in_company_size(company_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Company size is 51-200 or 1-10",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(
                PredicateField.COMPANY_SIZE,
                PredicateOperator.IN,
                ["51-200", "1-10"],
            ),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(company_prospects, spec)
    assert len(result) == 2
    names = {c.company_name for c in result}
    assert names == {"Acme Corp", "TestCo"}


def test_tier1_filter_company_exists_linkedin_url(company_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Must have linkedin_url",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(
                PredicateField.LINKEDIN_URL, PredicateOperator.EXISTS, None
            ),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(company_prospects, spec)
    assert len(result) == 2
    names = {c.company_name for c in result}
    assert names == {"Acme Corp", "TestCo"}


def test_tier1_filter_company_exclusion_exists_linkedin_url(
    company_prospects,
):
    criteria = [
        Criterion(
            id="c1",
            description="Must NOT have linkedin_url",
            kind=CriterionKind.EXCLUSION,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_exclusion_predicate(
                PredicateField.LINKEDIN_URL, PredicateOperator.EXISTS, None
            ),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(company_prospects, spec)
    assert len(result) == 1
    assert result[0].company_name == "Globex"


def test_tier1_filter_company_eq_region(company_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Region is EMEA",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(
                PredicateField.REGION, PredicateOperator.EQ, "EMEA"
            ),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(company_prospects, spec)
    assert len(result) == 1
    assert result[0].company_name == "TestCo"


def test_tier1_filter_case_insensitive_eq(individual_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="Country is australia (lowercase)",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.COUNTRY, PredicateOperator.EQ, "australia"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(individual_prospects, spec)
    assert len(result) == 3


def test_tier1_filter_extra_fields(individual_prospects):
    # Add a prospect with an extra field that matches
    prospects = list(individual_prospects)
    prospects.append(
        Prospect(
            full_name="Alice Lee",
            first_name="Alice",
            last_name="Lee",
            job_title="Engineer",
            company_name="StartupX",
            city="Sydney",
            country="Australia",
            extra_fields={"industry": "SaaS"},
            source_file="leads.csv",
            source_row=5,
        ),
    )
    criteria = [
        Criterion(
            id="c1",
            description="Company is StartupX",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.COMPANY_NAME, PredicateOperator.EQ, "StartupX"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(prospects, spec)
    assert len(result) == 1
    assert result[0].full_name == "Alice Lee"


def test_tier1_filter_neq_operator(individual_prospects):
    criteria = [
        Criterion(
            id="c1",
            description="City is not Brisbane",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.CITY, PredicateOperator.NEQ, "Brisbane"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(individual_prospects, spec)
    assert len(result) == 2
    cities = {p.city for p in result}
    assert cities == {"Sydney", "Melbourne"}


def _numeric_prospects():
    """Prospects with numeric-string company names for numeric operator tests."""
    return [
        Prospect(
            full_name="Person A",
            first_name="Person",
            last_name="A",
            job_title="Engineer",
            company_name="50",
            source_file="f.csv",
            source_row=1,
        ),
        Prospect(
            full_name="Person B",
            first_name="Person",
            last_name="B",
            job_title="Engineer",
            company_name="200",
            source_file="f.csv",
            source_row=2,
        ),
        Prospect(
            full_name="Person C",
            first_name="Person",
            last_name="C",
            job_title="Engineer",
            company_name="not_a_number",
            source_file="f.csv",
            source_row=3,
        ),
    ]


def test_tier1_filter_gt_operator():
    prospects = _numeric_prospects()
    criteria = [
        Criterion(
            id="c1",
            description="Company name > 100",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.COMPANY_NAME, PredicateOperator.GT, "100"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(prospects, spec)
    assert len(result) == 1
    assert result[0].company_name == "200"


def test_tier1_filter_gte_operator():
    prospects = _numeric_prospects()
    criteria = [
        Criterion(
            id="c1",
            description="Company name >= 50",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.COMPANY_NAME, PredicateOperator.GTE, "50"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(prospects, spec)
    assert len(result) == 2
    names = {p.company_name for p in result}
    assert names == {"50", "200"}


def test_tier1_filter_lt_operator():
    prospects = _numeric_prospects()
    criteria = [
        Criterion(
            id="c1",
            description="Company name < 100",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.COMPANY_NAME, PredicateOperator.LT, "100"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(prospects, spec)
    assert len(result) == 1
    assert result[0].company_name == "50"


def test_tier1_filter_lte_operator():
    prospects = _numeric_prospects()
    criteria = [
        Criterion(
            id="c1",
            description="Company name <= 200",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.COMPANY_NAME, PredicateOperator.LTE, "200"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(prospects, spec)
    assert len(result) == 2
    names = {p.company_name for p in result}
    assert names == {"50", "200"}


def test_tier1_filter_between_operator():
    prospects = _numeric_prospects()
    criteria = [
        Criterion(
            id="c1",
            description="Company name between 50 and 200",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=FieldPredicate(
                field=PredicateField.COMPANY_NAME,
                operator=PredicateOperator.BETWEEN,
                value="50",
                upper_value="200",
            ),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(prospects, spec)
    assert len(result) == 2
    names = {p.company_name for p in result}
    assert names == {"50", "200"}


def test_tier1_filter_numeric_operator_on_non_numeric_value_returns_false():
    prospects = _numeric_prospects()
    criteria = [
        Criterion(
            id="c1",
            description="Company name > 100",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(PredicateField.COMPANY_NAME, PredicateOperator.GT, "100"),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(prospects, spec)
    # "not_a_number" cannot be converted to float, so it is excluded
    assert len(result) == 1
    assert result[0].company_name == "200"


def test_expand_geo_predicate_country_eq():
    checks = set(_expand_geo_predicate("country", "eq", "Australia"))
    assert ("country", "eq", "Australia") in checks
    assert ("state", "eq", "victoria") in checks
    assert ("state", "eq", "nsw") in checks
    assert ("city", "eq", "melbourne") in checks
    assert ("city", "eq", "taringa") in checks
    assert len(checks) == 1 + 6 + 4  # country + 6 states + 4 cities


def test_expand_geo_predicate_country_in():
    checks = _expand_geo_predicate("country", "in", ["Australia"])
    assert checks[0] == ("country", "in", ["Australia"])
    assert ("state", "eq", "vic") in checks
    assert ("city", "eq", "melbourne") in checks


def test_expand_geo_predicate_non_country_passes_through():
    assert _expand_geo_predicate("city", "eq", "Sydney") == [("city", "eq", "Sydney")]
    assert _expand_geo_predicate("country", "contains", "Aus") == [
        ("country", "contains", "Aus")
    ]


def test_expand_geo_predicate_unknown_country_no_expansion():
    assert _expand_geo_predicate("country", "eq", "Nowhere") == [
        ("country", "eq", "Nowhere")
    ]


def test_tier1_filter_country_eq_matches_unenriched_state_and_city():
    # Legacy records: country was never enriched, state/city remain.
    prospects = [
        Prospect(
            full_name="Alice Lee",
            first_name="Alice",
            last_name="Lee",
            state="Victoria",
            city="Melbourne",
            source_file="leads.csv",
            source_row=1,
        ),
        Prospect(
            full_name="Bob Lee",
            first_name="Bob",
            last_name="Lee",
            state="Queensland",
            source_file="leads.csv",
            source_row=2,
        ),
        Prospect(
            full_name="Carol Lee",
            first_name="Carol",
            last_name="Lee",
            country="Canada",
            source_file="leads.csv",
            source_row=3,
        ),
    ]
    criteria = [
        Criterion(
            id="c1",
            description="Must be in Australia",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(
                PredicateField.COUNTRY, PredicateOperator.EQ, "Australia"
            ),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(prospects, spec)
    assert {p.full_name for p in result} == {"Alice Lee", "Bob Lee"}


def test_tier1_filter_country_in_matches_unenriched_city():
    prospects = [
        Prospect(
            full_name="Sam Lee",
            first_name="Sam",
            last_name="Lee",
            city="Sydney",
            source_file="leads.csv",
            source_row=1,
        ),
        Prospect(
            full_name="Tim Lee",
            first_name="Tim",
            last_name="Lee",
            country="Germany",
            source_file="leads.csv",
            source_row=2,
        ),
    ]
    criteria = [
        Criterion(
            id="c1",
            description="Must be in Australia or Canada",
            kind=CriterionKind.REQUIREMENT,
            evaluation_mode=EvaluationMode.STRUCTURED,
            predicate=_requirement_predicate(
                PredicateField.COUNTRY, PredicateOperator.IN, ["Australia", "Canada"]
            ),
        ),
    ]
    spec = _spec(criteria)
    result = tier1_filter(prospects, spec)
    assert [p.full_name for p in result] == ["Sam Lee"]
