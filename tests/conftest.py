"""Pytest configuration and shared fixtures for Nirite tests.

Registers ``live`` and ``slow`` markers and deselects ``live`` by default so
offline tests run without network or LLM API access.
"""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "live: tests that call real LLM APIs (deselected by default)."
    )
    config.addinivalue_line("markers", "slow: tests that take a long time to run.")


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Deselect ``live`` tests unless explicitly requested with ``-m live``."""
    if config.getoption("-m", None) == "live":
        # User explicitly asked for live tests; keep them.
        return
    skip_live = pytest.mark.skip(reason="need --run-live or -m live to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
