import pandas as pd
import pytest

from nirite.ingestion.company_normalizer import (
    cleanup_header as clean_header,
    company_alias_mapping,
    get_cleaned_columns,
    normalise_company_file,
)
from nirite.models.company import CompanyProspect


def test_clean_header():
    assert clean_header("Company Name") == "company name"
    assert clean_header("  Industry-Sector  ") == "industry sector"
    assert clean_header("   LinkedIn_URL    ") == "linked in url"


def test_normalise_company_file(tmp_path):
    source = tmp_path / "companies.csv"

    pd.DataFrame({
        "Company": [
            "Acme Corp",
            "JPMorgan Chase",
            "Stealth AI",
            "UNSW Partners",
        ],
        "Industry": [
            "Logistics",
            "Financial Services",
            "Artificial Intelligence",
            "Education",
        ],
        "Company Size": [
            "51-200",
            "10001+",
            "1-10",
            "11-50",
        ],
        "Region": [
            "APAC",
            "North America",
            "EMEA",
            "APAC",
        ],
        "Country": [
            "Australia",
            "United States",
            "United Kingdom",
            "Australia",
        ],
        "Website": [
            "https://acme.example.com",
            "https://jpmorganchase.com",
            "",
            "https://unswpartners.example.edu.au",
        ],
        "Contacted on": [
            "2023-01-01",
            "2023-02-15",
            "2023-03-10",
            "2023-04-20",
        ],
        "Replied": [True, False, True, False],
    }).to_csv(source, index=False)

    companies = normalise_company_file(source)

    # All records are ingested.
    assert len(companies) == 4

    # Canonical field mapping.
    assert companies[0].company_name == "Acme Corp"
    assert companies[0].industry == "Logistics"
    assert companies[0].company_size == "51-200"
    assert companies[0].region == "APAC"
    assert companies[0].country == "Australia"
    assert companies[0].company_website == "https://acme.example.com"

    assert companies[1].company_name == "JPMorgan Chase"
    assert companies[1].company_size == "10001+"

    # Empty website becomes None.
    assert companies[2].company_website is None

    # Extra fields are preserved.
    assert companies[0].extra_fields["contacted on"] == "2023-01-01"
    assert companies[0].extra_fields["replied"] == "True"

    assert companies[1].extra_fields["contacted on"] == "2023-02-15"

    # Source tracking.
    assert companies[0].source_file == "companies.csv"
    assert companies[0].source_row == 2
    assert companies[3].source_row == 5


def test_alias_mapping():
    df = pd.DataFrame(columns=[
        "Company",
        "Industry",
        "Size",
        "Website",
        "LinkedIn",
        "Region",
        "Country",
        "Description",
    ])
    df.columns = get_cleaned_columns(df)
    mapped = company_alias_mapping(df)

    assert mapped == {
        "company": "company_name",
        "industry": "industry",
        "size": "company_size",
        "website": "company_website",
        "linked in": "linkedin_url",
        "region": "region",
        "country": "country",
        "description": "description",
    }

    # Unknown columns remain unmapped.
    assert "notes" not in mapped


def test_alias_collision_keeps_one_winner_and_warns():
    df = pd.DataFrame(columns=["Company", "Company Name", "Industry", "Sector"])
    df.columns = get_cleaned_columns(df)

    with pytest.warns(UserWarning, match="Several columns match"):
        mapped = company_alias_mapping(df)

    # "company name" outranks "company"; "industry" outranks "sector"
    assert mapped == {
        "company name": "company_name",
        "industry": "industry",
    }


def test_canonical_named_column_wins_over_alias_and_nothing_is_dropped(tmp_path):
    source = tmp_path / "c.csv"
    source.write_text(
        "Company Name,Company,Region\nAcme,AU,APAC\n"
    )

    with pytest.warns(UserWarning):
        company = normalise_company_file(source)[0]

    assert company.company_name == "Acme"
    assert company.extra_fields["company"] == "AU"


def test_company_model_dump_roundtrip():
    company = CompanyProspect(
        company_name="Acme",
        industry="Logistics",
        company_size="51-200",
        region="APAC",
        extra_fields={"source": "manual"},
        source_file="companies.csv",
        source_row=2,
    )

    dumped = company.model_dump(mode="json")
    assert dumped["company_name"] == "Acme"
    assert dumped["industry"] == "Logistics"
    assert dumped["extra_fields"] == {"source": "manual"}

    restored = CompanyProspect.model_validate(dumped | {
        "source_file": "companies.csv",
        "source_row": 2,
    })
    assert restored.company_name == "Acme"
    assert restored.industry == "Logistics"
