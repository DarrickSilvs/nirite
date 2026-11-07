import pytest

from nirite.models.prospect import Prospect
from nirite.ingestion.reassignment import (
    delete_extra_field,
    get_all_fields,
    get_canonical_fields,
    get_extra_fields,
    reassign_field,
)

def make_prospect(**kwargs) -> Prospect:
    defaults = {
        "source_file": "contacts.csv",
        "source_row": 2,
    }
    return Prospect(**(defaults | kwargs))

def test_canonical_fields_follow_schema_order():
    fields = get_canonical_fields()

    assert fields == [
        "full_name",
        "first_name",
        "last_name",
        "job_title",
        "company_name",
        "company_domain",
        "company_website",
        "profile_url",
        "email",
        "country",
        "state",
        "city"
    ]

def test_move_canonical_value_to_empty_extra_field():
    prospect = make_prospect(company_name="Acme")
    prospects = [prospect]

    reassign_field(
        prospects,
        "canonical",
        "company_name",
        "extra",
        "Company",
    )

    assert prospect.company_name is None
    assert prospect.extra_fields["Company"] == "Acme"

def test_swap_two_populated_canonical_fields():
    prospect = make_prospect(
        company_name="Acme",
        job_title="Engineer",
    )

    reassign_field(
        [prospect],
        "canonical",
        "company_name",
        "canonical",
        "job_title",
    )

    assert prospect.company_name == "Engineer"
    assert prospect.job_title == "Acme"


def test_swap_is_applied_to_every_row_including_one_sided_rows():
    rows = [
        make_prospect(company_name="Engineer", job_title="Acme"),
        make_prospect(company_name="Engineer"),
        make_prospect(job_title="Acme"),
    ]

    reassign_field(rows, "canonical", "company_name", "canonical", "job_title")

    assert [(r.company_name, r.job_title) for r in rows] == [
        ("Acme", "Engineer"),
        (None, "Engineer"),
        ("Acme", None),
    ]


def test_move_into_completely_empty_destination_clears_source():
    rows = [make_prospect(company_name="Acme"), make_prospect()]

    reassign_field(rows, "canonical", "company_name", "extra", "Company")

    assert rows[0].company_name is None
    assert rows[0].extra_fields == {"Company": "Acme"}
    assert rows[1].extra_fields == {}


def test_swap_with_extra_field_does_not_leave_empty_keys():
    rows = [
        make_prospect(extra_fields={"Company": "Acme"}),
        make_prospect(company_name="Beta"),
    ]

    reassign_field(rows, "canonical", "company_name", "extra", "Company")

    assert rows[0].company_name == "Acme"
    assert rows[0].extra_fields == {}
    assert rows[1].company_name is None
    assert rows[1].extra_fields == {"Company": "Beta"}


def test_identical_fields_are_rejected():
    prospect = make_prospect(company_name="Acme")

    with pytest.raises(ValueError, match="different"):
        reassign_field(
            [prospect],
            "canonical",
            "company_name",
            "canonical",
            "company_name",
        )

def test_delete_extra_field_from_all_records():
    prospects = [
        make_prospect(
            extra_fields={"Campaign Notes": "Interested"}
        ),
        make_prospect(
            source_row=3,
            extra_fields={"Campaign Notes": "Follow up"},
        ),
    ]

    delete_extra_field(prospects, "Campaign Notes")

    assert get_extra_fields(prospects) == []
    assert all(
        "Campaign Notes" not in p.extra_fields
        for p in prospects
    )

def test_get_all_fields_includes_extra_fields():
    prospect = make_prospect(
        extra_fields={"Campaign Notes": "Interested"}
    )

    fields = get_all_fields([prospect])

    assert fields[0] == ("canonical", "full_name", "full_name")
    assert (
        "extra",
        "Campaign Notes",
        "extra: Campaign Notes",
    ) in fields