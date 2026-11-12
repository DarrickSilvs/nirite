import json
from pathlib import PureWindowsPath

import pytest
from typer.testing import CliRunner

from nirite.cli import app, get_filename

RECORD = {
    "full_name": "A B",
    "company_name": "Acme",
    "job_title": "CEO",
    "source_file": "f.csv",
    "source_row": 2,
    "extra_fields": {},
}
# field numbers: 1 full_name, 2 first_name, 3 last_name, 4 job_title, 5 company_name ...

COMPANY_RECORD = {
    "company_name": "Acme",
    "industry": "Technology",
    "source_file": "companies.csv",
    "source_row": 2,
    "extra_fields": {},
}
# company field numbers: 1 company_name, 2 company_domain, 3 company_website,
# 4 industry, 5 company_size ...


@pytest.fixture
def prospects_file(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps([RECORD]))
    return f


@pytest.fixture
def companies_file(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps([COMPANY_RECORD]))
    return f


def load(f):
    return json.loads(f.read_text())[0]


def test_declining_new_field_does_not_crash_or_change_data(prospects_file):
    result = CliRunner().invoke(app, ["map", str(prospects_file)], input="1\n5\n99\nn\n0\n")
    assert result.exit_code == 0
    assert result.exception is None
    assert load(prospects_file)["company_name"] == "Acme"


def test_declining_does_not_reuse_previous_destination(prospects_file):
    # swap company(5)<->title(4), then decline a new-field prompt for full_name
    result = CliRunner().invoke(
        app, ["map", str(prospects_file)], input="1\n5\n4\n1\n1\n99\nn\n0\n"
    )
    out = load(prospects_file)
    assert result.exit_code == 0
    assert out["full_name"] == "A B"          # untouched by the declined action
    assert out["job_title"] == "Acme" and out["company_name"] == "CEO"


def test_empty_new_field_name_is_rejected(prospects_file):
    result = CliRunner().invoke(app, ["map", str(prospects_file)], input="1\n5\n99\ny\n   \n0\n")
    assert result.exit_code == 0
    assert load(prospects_file)["company_name"] == "Acme"


def test_edits_are_saved_even_if_session_aborts(prospects_file):
    # one successful swap, then EOF on the next prompt aborts the session
    CliRunner().invoke(app, ["map", str(prospects_file)], input="1\n5\n4\n")
    out = load(prospects_file)
    assert out["job_title"] == "Acme" and out["company_name"] == "CEO"


def test_get_filename_returns_plain_stem():
    result = get_filename("customers")
    assert result is not None
    assert str(result) == "customers"


def test_get_filename_posix_path_input():
    result = get_filename("data/raw/customers.csv")
    assert result is not None
    assert str(result).endswith("customers.csv")


def test_get_filename_windows_backslash_on_linux():
    result = get_filename(r"data\raw\customers")
    assert result is not None
    assert isinstance(result, PureWindowsPath)
    assert "\\" in str(result)


def test_get_filename_never_returns_none():
    for stem in ["customers", "data/raw/customers.csv", "file", "a.b.c"]:
        assert get_filename(stem) is not None


def test_map_detects_company_record_and_maps_company_field(companies_file):
    # Move company_name (field 1) into a new extra field "Account".
    result = CliRunner().invoke(
        app, ["map", str(companies_file)],
        input="1\n1\n99\ny\nAccount\n0\n",
    )
    assert result.exit_code == 0
    assert result.exception is None
    out = load(companies_file)
    assert out["company_name"] is None
    assert out["extra_fields"] == {"account": "Acme"}


def test_ingest_default_output_path_is_stem_json(tmp_path):
    input_file = tmp_path / "customers.csv"
    input_file.write_text("full_name,company_name\nA B,Acme\n", encoding="utf-8")

    destination = tmp_path / "out" / "customers.json"
    result = CliRunner().invoke(
        app, ["ingest", str(input_file), "--output", str(destination)]
    )
    assert result.exit_code == 0
    assert destination.exists()
    data = json.loads(destination.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["full_name"] == "A B"

    # No None.json artifact is produced anywhere under the temp tree.
    assert not list(tmp_path.rglob("None.json"))
