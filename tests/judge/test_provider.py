"""Tests for judge provider factory (TASK-09)."""

from __future__ import annotations

import pytest

from nirite.judge.provider import (
    build_judge_providers,
    get_judge_provider,
)


def test_build_judge_providers_uses_existing_stack(monkeypatch) -> None:
    """Providers are built from existing Ministral/Gemini keys, no new env vars."""
    monkeypatch.setenv("MISTRAL_OPENROUTER_API_KEY", "test-mistral-key")
    monkeypatch.setenv("GEMINI_FLASH_LITE_API_KEY", "test-gemini-key")

    providers = build_judge_providers()
    assert len(providers) == 2
    names = [name for name, _ in providers]
    assert "Ministral" in names
    assert "Gemini" in names

    ministral = dict(providers)["Ministral"]
    gemini = dict(providers)["Gemini"]
    assert ministral.model == "openrouter/mistralai/ministral-3b-2512"
    assert gemini.model == "gemini/gemini-3.1-flash-lite"


def test_get_judge_provider_default_is_ministral(monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_OPENROUTER_API_KEY", "test-mistral-key")
    monkeypatch.setenv("GEMINI_FLASH_LITE_API_KEY", "test-gemini-key")

    provider = get_judge_provider()
    assert provider.model == "openrouter/mistralai/ministral-3b-2512"


def test_get_judge_provider_backup_is_gemini(monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_OPENROUTER_API_KEY", "test-mistral-key")
    monkeypatch.setenv("GEMINI_FLASH_LITE_API_KEY", "test-gemini-key")

    provider = get_judge_provider(backup=True)
    assert provider.model == "gemini/gemini-3.1-flash-lite"


def test_missing_mistral_key_raises_clear_error(monkeypatch) -> None:
    monkeypatch.delenv("MISTRAL_OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_FLASH_LITE_API_KEY", "test-gemini-key")

    with pytest.raises(RuntimeError, match="MISTRAL_OPENROUTER_API_KEY"):
        get_judge_provider()


def test_missing_gemini_key_raises_clear_error(monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_OPENROUTER_API_KEY", "test-mistral-key")
    monkeypatch.delenv("GEMINI_FLASH_LITE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GEMINI_FLASH_LITE_API_KEY"):
        get_judge_provider(backup=True)


def test_no_secret_in_exception_text(monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_OPENROUTER_API_KEY", "super-secret-key-12345")
    monkeypatch.delenv("GEMINI_FLASH_LITE_API_KEY", raising=False)

    try:
        get_judge_provider()
    except RuntimeError as exc:
        exc_text = str(exc)
        assert "super-secret-key-12345" not in exc_text
    else:
        raise AssertionError("expected RuntimeError for missing Gemini key")
