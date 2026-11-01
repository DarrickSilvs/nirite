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


def test_empty_source_does_not_change_destination():
    prospect = make_prospect(
        company_name=None,
        extra_fields={"Company": "Acme"},
    )

    reassign_field(
        [prospect],
        "canonical",
        "company_name",
        "extra",
        "Company",
    )

    assert prospect.company_name is None
    assert prospect.extra_fields["Company"] == "Acme"

def test_identical_fields_are_rejected():
    prospect = make_prospect(company_name="Acme")

    try:
        reassign_field(
            [prospect],
            "canonical",
            "company_name",
            "canonical",
            "company_name",
        )
    except ValueError as exc:
        assert "different" in str(exc)
    else:
        raise AssertionError("Expected ValueError")

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