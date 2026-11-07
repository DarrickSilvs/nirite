import json

import pytest
from typer.testing import CliRunner

from nirite.cli import app

RECORD = {
    "full_name": "A B",
    "company_name": "Acme",
    "job_title": "CEO",
    "source_file": "f.csv",
    "source_row": 2,
    "extra_fields": {},
}
# field numbers: 1 full_name, 2 first_name, 3 last_name, 4 job_title, 5 company_name ...


@pytest.fixture
def prospects_file(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps([RECORD]))
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
