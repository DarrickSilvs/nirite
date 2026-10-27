import re
from pathlib import Path

import pandas as pd
from rich.table import header
from nirite.schemas import Prospect

# Set of common field aliases
ALIASES = {
    "full_name": ["name", "full name", "fullname", "contact name"],
    "first_name": ["first name", "firstname", "given name"],
    "last_name": ["last name", "lastname", "surname", "family name"],
    "job_title": ["title", "job title", "position", "role"],
    "company_name": ["company", "company name", "organization", 
                     "org name", "organisation", "org", 
                     "organization name", "organisation name"
                     "company/organization", "company/organisation",
                     "workplace", "employer", "place of work"],
    "company_domain": ["domain", "company domain", "organization domain", 
                       "org domain", "organisation domain"],
    "company_website": ["website", "company website", "organization website",
                        "org website", "organisation website"],
    "profile_url": ["profile", "profile url", "linkedin profile",
                    "linkedin url", "linkedin link", "social profile", "linkedin"],
    "email": ["email", "email address", "e-mail", 
              "e-mail address", "work email",
              "work email address", "personal email", 
              "personal email address", "contact email",],
}

'''
Cleans up header values containing _, -, and whitespace
Replaces it with a single space and converts to lowercase
'''
def cleanup_header(value: str) -> str:
    value = value.strip().lower()
    return re.sub(r'[_\-\s]+', ' ', value)

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
    original_columns = list(df.columns)
    cleaned_columns = [cleanup_header(col) for col in original_columns]

    if len(set(cleaned_columns)) != len(cleaned_columns):
        raise ValueError("Duplicate column names after normalisation")

    return cleaned_columns

def alias_mapping(df: pd.DataFrame) -> dict[str, str]:
    aliases = {
        cleanup_header(alias): field
        for field, names in ALIASES.items()
        for alias in names
    }

    mapped = {
        column: aliases[column]
        for column in df.columns
        if column in aliases
    }

    targets = list(mapped.values())
    if len(set(targets)) != len(targets):
        raise ValueError(
            "Multiple columns mapped to the same field."
            "Please ensure unique column names."
        )

    return mapped

def get_record_fields(
        record: dict[str, str | None]
        ) -> tuple[dict[str, str | None], 
                   dict[str, str | None], 
                   dict[str, str | None]]:
    
    canonical_fields = set(Prospect.model_fields) - {
        "source_file", "source_row", "extra_fields"
    }

    values = {
        key: (value.strip() or None)
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
        prospects.append(
            Prospect(
                **known_fields,
                extra_fields=extra_fields,
                source_file=path.name,
                source_row=index,
            )
        )

    return prospects
        

    