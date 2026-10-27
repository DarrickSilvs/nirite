import pandas as pd

from nirite.ingestion.normalizer import (
    cleanup_header,
    normalise_file,
    alias_mapping,
    get_cleaned_columns,
)

def test_cleanup_header():
    assert cleanup_header("First     Name") == "first name"
    assert cleanup_header("  Last-Name  ") == "last name"
    assert cleanup_header("   Email_Address    ") == "email address"


def test_normalise_file(tmp_path):
    source = tmp_path / "contacts.csv"

    pd.DataFrame({
        "name": [
            "John 😭 Smith Doe",
            "Jane Doe Smith 😭",
            "😭",
            "你好",
        ],
        "Role": [
            "Aspiring Developer",
            "Senior Engineer | @UNSW",
            "Intern in JPM",
            "Managing Solutions for undeserved regions",
        ],
        "Org": [
            "UNSW",
            "JPMorgan",
            "Stealth Startup",
            "UNSW",
        ],
        "Contacted on": [
            "2023-01-01",
            "2023-02-15",
            "2023-03-10",
            "2023-04-20",
        ],
        "Replied": [True, False, True, False],
    }).to_csv(source, index=False)

    prospects = normalise_file(source)

    # All records are ingested.
    assert len(prospects) == 4

    # Name normalization.
    assert prospects[0].full_name == "John Smith Doe"
    assert prospects[0].first_name == "John Smith"
    assert prospects[0].last_name == "Doe"

    assert prospects[1].full_name == "Jane Doe Smith"
    assert prospects[1].first_name == "Jane Doe"
    assert prospects[1].last_name == "Smith"

    # Emoji-only name becomes None after cleaning.
    assert prospects[2].full_name is None
    assert prospects[2].first_name is None
    assert prospects[2].last_name is None

    # Non-Latin names are preserved.
    assert prospects[3].full_name == "你好"
    assert prospects[3].first_name == "你好"
    assert prospects[3].last_name == "你好"

    # Canonical field mapping.
    assert prospects[0].job_title == "Aspiring Developer"
    assert prospects[0].company_name == "UNSW"

    assert prospects[1].job_title == "Senior Engineer | @UNSW"
    assert prospects[1].company_name == "JPMorgan"

    # Emojis are removed from other text fields too.
    assert prospects[2].job_title == "Intern in JPM"
    assert prospects[2].company_name == "Stealth Startup"

    # Extra fields are preserved.
    assert prospects[0].extra_fields["contacted on"] == "2023-01-01"
    assert prospects[0].extra_fields["replied"] == "True"

    assert prospects[1].extra_fields["contacted on"] == "2023-02-15"
    assert prospects[1].extra_fields["replied"] == "False"

    # Source tracking.
    assert prospects[0].source_file == "contacts.csv"
    assert prospects[0].source_row == 2
    assert prospects[3].source_row == 5

def test_alias_mapping():
    df = pd.DataFrame(columns=[
        "Name",
        "First Name",
        "Last Name",
        "Position",
        "Organisation",
        "LinkedIn URL",
        "Email_Address",
        "Contacted On",
    ])

    df.columns = get_cleaned_columns(df)
    mapped = alias_mapping(df)

    assert mapped == {
        "name": "full_name",
        "first name": "first_name",
        "last name": "last_name",
        "position": "job_title",
        "organisation": "company_name",
        "linkedin url": "profile_url",
        "email address": "email",
    }

    # Unknown columns remain unmapped.
    assert "contacted on" not in mapped

def test_rejects_duplicate_targets():
    df = pd.DataFrame(columns=[
        "Name",
        "First Name",
        "Last Name",
        "Position",
        "Organisation",
        "LinkedIn URL",
        "Email_Address",
        "Contacted On",
        "Job Title",  # Duplicate target for Position
        "Company Name"
    ])

    df.columns = get_cleaned_columns(df)

    try:
        alias_mapping(df)
    except ValueError as e:
        assert str(e) == (
            "Multiple columns mapped to the same field."
            "Please ensure unique column names."
        )

