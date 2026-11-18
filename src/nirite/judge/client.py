"""Batched judge client: prompt, strict parse, one retry, optional cache.

Sends all questions for a subject in a single batched call, parses the
response as ``JudgeAnswer`` objects, and retries exactly once on parse
failure. Never returns a default verdict — raises ``JudgeError`` on failure.

Cache is opt-in via ``cache_dir`` and keyed by
``sha256(prompt_version|model|question_ids|subject_hash)``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from nirite.judge.models import JudgeAnswer, JudgeQuestion

MAX_QUESTIONS_PER_CALL = 12
PROMPT_VERSION = "1"


class JudgeError(RuntimeError):
    """Raised when the judge client cannot produce a valid verdict."""


def _load_prompt_template() -> str:
    template_path = Path(__file__).parent / "prompts" / "judge.md"
    return template_path.read_text(encoding="utf-8")


def _build_prompt(questions: list[JudgeQuestion], subject_data: dict) -> str:
    template = _load_prompt_template()
    questions_text = "\n".join(
        f"- {q.id}: {q.text} (answerable_from: {', '.join(q.answerable_from) or 'none'})"
        for q in questions
    )
    return template.replace("{questions}", questions_text).replace(
        "{subject_data}", json.dumps(subject_data, indent=2, ensure_ascii=False)
    )


def _cache_key(questions: list[JudgeQuestion], subject_data: dict) -> str:
    q_ids = "|".join(sorted(q.id for q in questions))
    subject_json = json.dumps(subject_data, sort_keys=True, ensure_ascii=False)
    raw = f"{PROMPT_VERSION}|{q_ids}|{subject_json}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_cache(cache_dir: Path, key: str) -> list[JudgeAnswer] | None:
    cache_file = cache_dir / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return [JudgeAnswer(**item) for item in data]
    except (json.JSONDecodeError, ValueError, TypeError, OSError):
        return None


def _write_cache(cache_dir: Path, key: str, answers: list[JudgeAnswer]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{key}.json"
    tmp = cache_dir / f"{key}.json.tmp"
    tmp.write_text(
        json.dumps([a.model_dump(mode="json") for a in answers], indent=2),
        encoding="utf-8",
    )
    tmp.replace(cache_file)


def _answers_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question_id": {"type": "string"},
                        "answer": {"type": "string", "enum": ["yes", "no", "unknown"]},
                        "evidence_field": {"type": ["string", "null"]},
                        "evidence_quote": {"type": ["string", "null"]},
                    },
                    "required": ["question_id", "answer"],
                },
            }
        },
        "required": ["answers"],
    }


class JudgeClient:
    """Batched judge client with strict parse, one retry, and optional cache."""

    def __init__(
        self,
        provider: Any,
        *,
        cache_dir: Path | str | None = None,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        self.provider = provider
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.prompt_version = prompt_version

    def judge(
        self,
        questions: list[JudgeQuestion],
        subject_data: dict,
    ) -> list[JudgeAnswer]:
        """Judge all questions for one subject, returning answers in question order."""
        if len(questions) > MAX_QUESTIONS_PER_CALL:
            raise JudgeError(f"exceeds max_questions_per_call={MAX_QUESTIONS_PER_CALL}")

        # Cache lookup
        if self.cache_dir:
            key = _cache_key(questions, subject_data)
            cached = _read_cache(self.cache_dir, key)
            if cached is not None:
                return cached

        prompt = _build_prompt(questions, subject_data)
        schema = _answers_schema()

        # Strict parse with exactly one repair retry
        response = self._call_with_retry(prompt, schema)

        # Parse into JudgeAnswer objects
        try:
            data = json.loads(response)
            answers = [JudgeAnswer(**item) for item in data["answers"]]
        except Exception as exc:
            raise JudgeError(f"failed to parse judge response: {exc}") from exc

        # Cache write
        if self.cache_dir:
            _write_cache(self.cache_dir, _cache_key(questions, subject_data), answers)

        return answers

    def _call_with_retry(self, prompt: str, schema: dict) -> str:
        """Call the provider, retrying exactly once on parse failure."""
        system_prompt = (
            "You are a strict bounded judge. Answer each question with yes/no/unknown. "
            "Return only valid JSON matching the supplied schema. No markdown fences, "
            "no commentary."
        )

        # First attempt
        try:
            response = self.provider.generate_json(system_prompt, prompt, schema)
            self._validate_response_shape(response)
            return response
        except Exception as first_error:  # noqa: BLE001 — retry on any provider failure
            # One repair retry
            retry_prompt = (
                f"{prompt}\n\n"
                f"Your previous response was invalid or unparseable: {first_error}\n"
                f"Return the same answers as one complete JSON object matching the schema. "
                f"Do not add commentary."
            )
            try:
                response = self.provider.generate_json(
                    system_prompt, retry_prompt, schema
                )
                self._validate_response_shape(response)
                return response
            except Exception as second_error:
                raise JudgeError(
                    f"judge failed after 2 attempts: {second_error}"
                ) from second_error

    def _validate_response_shape(self, response: str) -> None:
        """Minimal shape check — must be parseable JSON with an 'answers' array."""
        try:
            data = json.loads(response)
        except json.JSONDecodeError as exc:
            raise JudgeError(f"invalid JSON: {exc}") from exc
        if not isinstance(data, dict) or "answers" not in data:
            raise JudgeError("response missing 'answers' array")
        if not isinstance(data["answers"], list):
            raise JudgeError("'answers' is not an array")
