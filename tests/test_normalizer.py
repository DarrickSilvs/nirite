import pandas as pd
import pytest

from nirite.ingestion.normalizer import (
    cleanup_header,
    normalise_file,
)

def test_cleanup_header():
    assert cleanup_header("First     Name") == "first_name"
    assert cleanup_header("  Last-Name  ") == "last_name"
    assert cleanup_header("   Email_Address    ") == "email_address"
