import re
import warnings
from pathlib import Path
from typing import Callable, TypeVar

import emoji
import pandas as pd

from nirite.models.company import CompanyProspect
from nirite.models.prospect import Prospect

TModel = TypeVar("TModel")

# Set of common field aliases for individual prospects.
ALIASES = {
    "full_name": [
        "name", "full name", "fullname", "contact name",
    ],
    "first_name": [
        "first name", "firstname", "given name",
    ],
    "last_name": [
        "last name", "lastname", "surname", "family name",
    ],
    "job_title": [
        "title", "job title", "position", "role",
    ],
    "company_name": [
        "company", "company name", "organization",
        "org name", "organisation", "org",
        "organization name", "organisation name",
        "company/organization", "company/organisation",
        "workplace", "employer", "place of work",
    ],
    "company_domain": [
        "domain", "company domain", "organization domain",
        "org domain", "organisation domain",
    ],
    "company_website": [
        "company website", "organization website",
        "org website", "organisation website",
        "company url", "organization url", "org url",
        "organisation url",
    ],
    "profile_url": [
        "profile", "profile url", "linkedin profile",
        "linked in profile", "linkedin url", "linked in url",
        "linkedin link", "linked in link", "social profile",
        "linkedin", "linked in",
    ],
    "email": [
        "email", "email address", "e-mail",
        "e-mail address", "work email",
        "work email address", "personal email",
        "personal email address", "contact email",
    ],
    "country": [
        "country name", "nation", "based in country",
    ],
    "state": [
        "state/province", "province", "region", "state name",
    ],
    "city": [
        "town", "town name", "city name", "based in city"
    ]
}

# City/state -> country lookup used to enrich records that lack a country.
# Extensible: add entries for other countries under their own keys.
GEO_HIERARCHY: dict[str, dict[str, set[str]]] = {
    "Australia": {
        "cities": {"melbourne", "sydney", "brisbane", "taringa"},
        "states": {
            "victoria",
            "queensland",
            "new south wales",
            "nsw",
            "qld",
            "vic",
        },
    },
}

_CITY_STATE_TO_COUNTRY: dict[str, str] = {}
for _country, _hierarchy in GEO_HIERARCHY.items():
    for _city in _hierarchy["cities"]:
        _CITY_STATE_TO_COUNTRY[_city] = _country
    for _state in _hierarchy["states"]:
        _CITY_STATE_TO_COUNTRY[_state] = _country


def derive_country(
    country: str | None, city: str | None, state: str | None
) -> str | None:
    """Return the known country, else derive it from city/state via GEO_HIERARCHY.

    An already-set country always wins; unmatched city/state leaves country as None.
    """
    if country:
        return country
    for value in (city, state):
        if value:
            matched = _CITY_STATE_TO_COUNTRY.get(value.strip().lower())
            if matched:
                return matched
    return None


# Set of common field aliases for company prospects.
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


def cleanup_header(value: str) -> str:
    """Clean up header values containing _, -, and whitespace.

    Replaces with a single space and converts to lowercase.
    """
    value = value.strip()
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = re.sub(r"[\s_\-]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.lower()


def init_df(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")

    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str).fillna("")
    elif path.suffix.lower() in [".xlsm", ".xlsx"]:
        df = pd.read_excel(path, dtype=str).fillna("")
    else:
        raise ValueError("Supported format: CSV and XLSX/XLSM only")

    return df


def get_cleaned_columns(df: pd.DataFrame) -> list[str]:
    cleaned = [cleanup_header(str(col)) for col in df.columns]

    if len(set(cleaned)) != len(cleaned):
        raise ValueError(
            "Duplicate column names after header normalization. "
            "Rename the conflicting columns in the source file."
        )

    return cleaned


def build_alias_mapping(
    df: pd.DataFrame, aliases: dict[str, list[str]]
) -> dict[str, str]:
    """Map cleaned column names to canonical fields using an alias dict.

    Priority per field: a column already named after the canonical field wins,
    then aliases in the order listed. When several columns compete for one
    field, the winner is mapped and the others are left unmapped, so they are
    preserved in extra_fields. A warning names every demoted column.
    """
    candidates: dict[str, list[tuple[int, str]]] = {}

    for field, names in aliases.items():
        ranked = {cleanup_header(field): -1}
        for rank, alias in enumerate(names):
            ranked.setdefault(cleanup_header(alias), rank)

        for column in df.columns:
            if column in ranked:
                candidates.setdefault(field, []).append(
                    (ranked[column], column)
                )

    mapped: dict[str, str] = {}
    for field, found in candidates.items():
        found.sort()
        winner = found[0][1]
        mapped[winner] = field

        if len(found) > 1:
            demoted = ", ".join(repr(column) for _, column in found[1:])
            warnings.warn(
                f"Several columns match '{field}'. Using {winner!r}; "
                f"kept {demoted} as extra fields.",
                UserWarning,
                stacklevel=2,
            )

    return mapped


def split_record_fields(
    record: dict[str, str | None], model_class: type[TModel]
) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """Split a record into canonical fields (per model_class) and extra fields."""
    canonical_fields = set(model_class.model_fields) - {
        "source_file", "source_row", "extra_fields"
    }

    values = {
        key: (value.strip() or None) if value else None
        for key, value in record.items()
    }

    known_fields = {
        key: value
        for key, value in values.items()
        if key in canonical_fields
    }

    extra_fields = {
        key: value
        for key, value in values.items()
        if key not in canonical_fields
    }

    return known_fields, extra_fields


def clean_name_value(value: str | None) -> str | None:
    if value is None:
        return None
    # Remove emojis
    value = emoji.replace_emoji(value, replace="")
    value = " ".join(value.split())
    return value or None


def normalise_name_values(
    full_name: str | None,
    first_name: str | None,
    last_name: str | None,
) -> tuple[str | None, str | None, str | None]:
    full_name = clean_name_value(full_name)
    first_name = clean_name_value(first_name)
    last_name = clean_name_value(last_name)

    if not full_name and (first_name or last_name):
        full_name = " ".join(
            part for part in (first_name, last_name) if part
        )

    if full_name and (not first_name or not last_name):
        parts = full_name.split()
        if len(parts) == 1:
            first_name = first_name or parts[0]
            last_name = last_name or parts[0]
        elif len(parts) >= 2:
            first_name = first_name or " ".join(parts[:-1])
            last_name = last_name or parts[-1]

    return full_name, first_name, last_name


def _normalise_file_core(
    path: Path,
    model_class: type[TModel],
    aliases: dict[str, list[str]],
    clean_fields: Callable[[dict[str, str | None]], dict[str, str | None]] | None = None,
) -> list[TModel]:
    """Generic normalisation pipeline parameterized by model class and aliases.

    Reads a CSV/Excel file, cleans headers, maps canonical fields via aliases,
    iterates rows, splits canonical vs extra fields, optionally cleans fields,
    and returns model instances with source tracking.
    """
    df = init_df(path)
    df.columns = get_cleaned_columns(df)

    mapped = build_alias_mapping(df, aliases)
    df = df.rename(columns=mapped)

    results: list[TModel] = []

    for index, row in enumerate(
        df.to_dict(orient="records"), start=2
    ):
        known_fields, extra_fields = split_record_fields(row, model_class)

        if clean_fields is not None:
            known_fields = clean_fields(known_fields)

        # Geo-enrichment: derive country from city/state when it is missing.
        known_fields["country"] = derive_country(
            known_fields.get("country"),
            known_fields.get("city"),
            known_fields.get("state"),
        )

        results.append(
            model_class(
                **known_fields,
                extra_fields=extra_fields,
                source_file=path.name,
                source_row=index,
            )
        )

    return results


# --- Backward-compatible wrappers ---


def alias_mapping(df: pd.DataFrame) -> dict[str, str]:
    """Map cleaned column names to canonical individual-prospect fields."""
    return build_alias_mapping(df, ALIASES)


def get_record_fields(
    record: dict[str, str | None]
) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """Split a record into canonical Prospect fields and extra fields."""
    return split_record_fields(record, Prospect)


def _clean_individual_fields(
    known_fields: dict[str, str | None],
) -> dict[str, str | None]:
    full_name, first_name, last_name = normalise_name_values(
        known_fields.get("full_name"),
        known_fields.get("first_name"),
        known_fields.get("last_name"),
    )
    known_fields.update({
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
    })
    return known_fields


def normalise_file(path: Path) -> list[Prospect]:
    """Normalise an individual-prospect CSV/XLSX into a list of Prospect."""
    return _normalise_file_core(
        path,
        model_class=Prospect,
        aliases=ALIASES,
        clean_fields=_clean_individual_fields,
    )
