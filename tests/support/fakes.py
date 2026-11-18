"""Scripted LLM doubles for offline tests.

Provides ``FakeLLMProvider`` which returns canned responses in order, records
every call for assertions, and supports exhaustion and error injection.
"""

from __future__ import annotations


class FakeLLMProvider:
    """A scripted LLM provider that returns canned responses in order.

    Records every call as ``(system_prompt, user_prompt, schema)`` for
    assertions. Exhausts after all scripted responses are consumed.
    """

    def __init__(
        self,
        responses: list[str] | None = None,
        *,
        raises: type[Exception] | None = None,
    ) -> None:
        self._responses: list[str] = list(responses or [])
        self._raises = raises
        self.call_log: list[tuple[str, str, dict]] = []
        self.call_count = 0

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
    ) -> str:
        self.call_log.append((system_prompt, user_prompt, schema))
        self.call_count += 1

        if self._raises is not None:
            raise self._raises("fake provider error")

        if not self._responses:
            raise RuntimeError("FakeLLMProvider exhausted: no more scripted responses.")

        return self._responses.pop(0)

    def response(self, text: str) -> None:
        """Append a scripted response to the queue."""
        self._responses.append(text)
