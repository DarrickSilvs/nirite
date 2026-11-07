import re
import warnings
from pathlib import Path

import pandas as pd
import emoji

from nirite.models.prospect import Prospect

# Set of common field aliases
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

'''
Cleans up header values containing _, -, and whitespace
Replaces it with a single space and converts to lowercase
'''
def cleanup_header(value: str) -> str:
    value = value.strip()

    # Convert camelCase/PascalCase to spaces
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)

    value = re.sub(r'[_\-\s]+', ' ', value)
    value = re.sub(r'\s+', ' ', value)

    return value.lower()

def init_df(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Input file not found: {path}")

    if path.suffix.lower() == ".csv":
        # Specifies values to be str type and fills NaN values with ""
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

def alias_mapping(df: pd.DataFrame) -> dict[str, str]:
    """Map cleaned column names to canonical fields.

    Priority per field: a column already named after the canonical field wins,
    then aliases in the order listed in ALIASES. When several columns compete
    for one field, the winner is mapped and the others are left unmapped, so
    they are preserved in extra_fields. A warning names every demoted column.
    """
    candidates: dict[str, list[tuple[int, str]]] = {}

    for field, names in ALIASES.items():
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

def get_record_fields(
        record: dict[str, str | None]
        ) -> tuple[
            dict[str, str | None], 
            dict[str, str | None]]:
    
    canonical_fields = set(Prospect.model_fields) - {
        "source_file", "source_row", "extra_fields"
    }

    values = {
        key: (value.strip() or None) if value else None
        for key, value in record.items()}

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

def clean_name(value: str | None) -> str | None:
    if value is None:
        return None

    # Remove emojis
    value = emoji.replace_emoji(value, replace="")
    value = " ".join(value.split())

    return value or None

def normalise_name(
    full_name: str | None,
    first_name: str | None,
    last_name: str | None
) -> tuple[str | None, str | None, str | None]:
    full_name = clean_name(full_name)
    first_name = clean_name(first_name)
    last_name = clean_name(last_name)

    # Combine first and last name if full name empty
    if not full_name and (first_name or last_name):
        full_name = " ".join(
            part for part in (first_name, last_name) if part
        )

    # If either first or last name is empty, try to split full name
    if full_name and (not first_name or not last_name):
        parts = full_name.split()

        if len(parts) == 1:
            first_name = first_name or parts[0]
            last_name = last_name or parts[0]
        elif len(parts) >= 2:
            first_name = first_name or " ".join(parts[:-1])
            last_name = last_name or parts[-1]

    return full_name, first_name, last_name

def normalise_file(path: Path) -> list[Prospect]:
    df = init_df(path)
    df.columns = get_cleaned_columns(df)

    mapped = alias_mapping(df)
    df = df.rename(columns=mapped)

    prospects = []

    for index, row in enumerate(
        # orient="records" returns a list of dict
        # [{"full_name": "John Doe", "email": "john.doe@example.com",...},
        #  {"full_name": "Jane Smith", "email": "jane.smith@example.com",...}]
        df.to_dict(orient="records"), start=2
    ):
        known_fields, extra_fields = get_record_fields(row)

        full_name, first_name, last_name = normalise_name(
            full_name=known_fields.get("full_name"),
            first_name=known_fields.get("first_name"),
            last_name=known_fields.get("last_name"),
        )

        known_fields.update({
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
        })

        prospects.append(
            Prospect(
                **known_fields,
                extra_fields=extra_fields,
                source_file=path.name,
                source_row=index,
            )
        )

    return prospects
        

    