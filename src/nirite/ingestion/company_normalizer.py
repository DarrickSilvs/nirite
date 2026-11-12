import warnings
from pathlib import Path

import pandas as pd

from nirite.ingestion.normalizer import (
    cleanup_header,
    build_alias_mapping,
    split_record_fields,
    _normalise_file_core,
    get_cleaned_columns,
)
from nirite.models.company import CompanyProspect

clean_header = cleanup_header

COMPANY_ALIASES = {
    "company_name": [
        "company", "company name", "organization", "organisation", "org",
        "business name", "firm", "account", "client name", "customer name",
        "company/organization", "company/organisation", "workplace",
        "employer", "place of work",
    ],
    "company_domain": [
        "domain", "company domain", "organization domain", "org domain",
        "organisation domain", "website domain", "email domain",
    ],
    "company_website": [
        "company website", "organization website", "org website",
        "organisation website", "company url", "organization url", "org url",
        "organisation url", "website", "url", "homepage", "business website",
        "company site",
    ],
    "industry": [
        "industry", "sector", "vertical", "business type", "company industry",
        "organisation industry", "organization industry", "field", "niche",
        "market", "specialisation", "specialization",
    ],
    "company_size": [
        "company size", "size", "employee count", "number of employees",
        "employees", "headcount", "workforce size", "company headcount",
        "organisation size", "organization size", "company employees",
        "no of employees", "number of staff", "staff count",
    ],
    "region": [
        "region", "geographical region", "area", "territory", "location",
        "based in region", "geo", "sales region", "account region",
    ],
    "country": [
        "country", "country name", "nation", "based in country", "hq country",
        "headquarters country", "company country",
    ],
    "state": [
        "state", "state/province", "province", "state name",
    ],
    "city": [
        "city", "town", "city name", "town name", "based in city", "hq city",
        "company city",
    ],
    "linkedin_url": [
        "linkedin", "linked in", "linkedin profile", "linked in profile",
        "linkedin url", "linked in url", "linkedin link", "linked in link",
        "company linkedin", "company linkedin url", "company linkedin profile",
        "social profile",
    ],
    "description": [
        "description", "about", "company description", "business description",
        "about company", "summary", "overview", "company overview", "about us",
        "boilerplate",
    ],
}


def company_alias_mapping(df: pd.DataFrame) -> dict[str, str]:
    """Map cleaned column names to canonical company fields."""
    return build_alias_mapping(df, COMPANY_ALIASES)


def get_company_record_fields(
    record: dict[str, str | None]
) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """Split a record into canonical company fields and extra fields."""
    return split_record_fields(record, CompanyProspect)


def clean_company_name(value: str | None) -> str | None:
    """Trim and collapse whitespace in a company name."""
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


def normalise_company_file(path: Path) -> list[CompanyProspect]:
    """Normalise a company prospect CSV/XLSX into a list of CompanyProspect."""
    return _normalise_file_core(
        path,
        model_class=CompanyProspect,
        aliases=COMPANY_ALIASES,
    )
