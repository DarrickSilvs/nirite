"""Judge model provider factory and comparison harness.

Builds judge providers from Nirite's existing Ministral + Gemini stack
(via litellm/OpenRouter). No new env vars, no edits to the protected
``campaign/llm/providers.py``, no constrained decoding — uses the same
``json_object`` + retry path as the rest of Layer 1.

The factory exposes ``get_judge_provider()`` returning the recommended
default, with ``get_judge_provider(backup=True)`` returning the other.
Until you run the comparison harness against your real API keys, the
default is Ministral (matching your analyser stack's primary).

Run ``python -m nirite.judge.compare`` to benchmark both models as judges
against known-answer questions and pick the better default.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from nirite.campaign.llm.providers import (
    GEMINI_MODEL,
    OPENROUTER_MODEL,
    LiteLLMProvider,
    get_api_key,
)
from nirite.judge.client import JudgeClient
from nirite.judge.models import JudgeAnswerValue, JudgeQuestion


def build_judge_providers() -> list[tuple[str, LiteLLMProvider]]:
    """Build Ministral (primary) and Gemini (backup) judge providers.

    Uses the same API keys as the analyser/parser stack:
    ``MISTRAL_OPENROUTER_API_KEY`` and ``GEMINI_FLASH_LITE_API_KEY``.
    """
    ministral = LiteLLMProvider(
        api_key=get_api_key("MISTRAL_OPENROUTER_API_KEY"),
        model=OPENROUTER_MODEL,
    )
    gemini = LiteLLMProvider(
        api_key=get_api_key("GEMINI_FLASH_LITE_API_KEY"),
        model=GEMINI_MODEL,
    )
    return [
        ("Ministral", ministral),
        ("Gemini", gemini),
    ]


def get_judge_provider(*, backup: bool = False) -> LiteLLMProvider:
    """Return the recommended judge provider.

    Default (backup=False): Ministral — matches your analyser primary.
    backup=True: Gemini — your analyser backup.

    Run the comparison harness (``python -m nirite.judge.compare``) against
    your real API keys to verify which is better for judging, then flip the
    default here if needed.
    """
    providers = build_judge_providers()
    if backup:
        return providers[1][1]
    return providers[0][1]


def get_judge_client(
    *,
    backup: bool = False,
    cache_dir: Path | str | None = None,
) -> JudgeClient:
    """Return a ``JudgeClient`` wired to the recommended judge provider."""
    provider = get_judge_provider(backup=backup)
    return JudgeClient(provider, cache_dir=cache_dir)


# ---------------------------------------------------------------------------
# Comparison harness
# ---------------------------------------------------------------------------

KNOWN_ANSWER_QUESTIONS: list[dict] = [
    {
        "criterion_id": "c1",
        "question": "Is the prospect based in Australia?",
        "answerable_from": ["country"],
        "subject_data": {"country": "Australia"},
        "expected": JudgeAnswerValue.YES,
    },
    {
        "criterion_id": "c1",
        "question": "Is the prospect based in Australia?",
        "answerable_from": ["country"],
        "subject_data": {"country": "Germany"},
        "expected": JudgeAnswerValue.NO,
    },
    {
        "criterion_id": "c1",
        "question": "Is the prospect based in Australia?",
        "answerable_from": ["country"],
        "subject_data": {},
        "expected": JudgeAnswerValue.UNKNOWN,
    },
    {
        "criterion_id": "c2",
        "question": "Is the company in the SaaS industry?",
        "answerable_from": ["industry"],
        "subject_data": {"industry": "SaaS"},
        "expected": JudgeAnswerValue.YES,
    },
    {
        "criterion_id": "c2",
        "question": "Is the company in the SaaS industry?",
        "answerable_from": ["industry"],
        "subject_data": {"industry": "Retail"},
        "expected": JudgeAnswerValue.NO,
    },
]


def _make_questions(items: list[dict]) -> list[JudgeQuestion]:
    return [
        JudgeQuestion(
            id=f"q{i}",
            text=item["question"],
            criterion_id=item["criterion_id"],
            answerable_from=item["answerable_from"],
        )
        for i, item in enumerate(items)
    ]


def compare_judge_models() -> dict:
    """Run both Ministral and Gemini through known-answer judge questions.

    Returns a report with per-model accuracy, latency, and parse success
    rate. Requires real API keys (MISTRAL_OPENROUTER_API_KEY,
    GEMINI_FLASH_LITE_API_KEY) — skips gracefully if missing.
    """
    providers = build_judge_providers()
    results: dict[str, dict] = {}

    for name, provider in providers:
        model_result: dict[str, Any] = {
            "model": provider.model,
            "correct": 0,
            "total": 0,
            "parse_success": 0,
            "parse_fail": 0,
            "latency_seconds": 0.0,
            "error": None,
        }

        client = JudgeClient(provider)

        for item in KNOWN_ANSWER_QUESTIONS:
            q = JudgeQuestion(
                id=item["criterion_id"],
                text=item["question"],
                criterion_id=item["criterion_id"],
                answerable_from=item["answerable_from"],
            )
            start = time.perf_counter()
            try:
                answers = client.judge([q], item["subject_data"])
                elapsed = time.perf_counter() - start
                model_result["latency_seconds"] += elapsed
                model_result["total"] += 1
                if answers:
                    model_result["parse_success"] += 1
                    if answers[0].answer == item["expected"]:
                        model_result["correct"] += 1
                else:
                    model_result["parse_fail"] += 1
            except Exception as exc:  # noqa: BLE001 — record and continue
                model_result["error"] = str(exc)
                model_result["total"] += 1

        if model_result["total"] > 0:
            model_result["accuracy"] = model_result["correct"] / model_result["total"]
            model_result["parse_rate"] = (
                model_result["parse_success"] / model_result["total"]
            )
            model_result["avg_latency"] = (
                model_result["latency_seconds"] / model_result["total"]
            )
        else:
            model_result["accuracy"] = 0.0
            model_result["parse_rate"] = 0.0
            model_result["avg_latency"] = 0.0

        results[name] = model_result

    # Determine recommended default
    best = max(
        results.items(),
        key=lambda kv: (kv[1]["accuracy"], kv[1]["parse_rate"], -kv[1]["avg_latency"]),
    )[0]

    return {
        "recommended_default": best,
        "models": results,
        "prompt_version": "1",
        "note": "Edit get_judge_provider() to flip the default if Gemini scores higher.",
    }


def compare_cli() -> None:
    """CLI entry point: python -m nirite.judge.compare"""
    import sys

    try:
        report = compare_judge_models()
    except Exception as exc:  # noqa: BLE001 — report error cleanly
        print(f"Comparison failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(report, indent=2))
    print(f"\nRecommended default judge model: {report['recommended_default']}")


if __name__ == "__main__":
    compare_cli()
