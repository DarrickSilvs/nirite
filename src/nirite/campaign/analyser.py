import json
import time
from pathlib import Path

from pydantic import ValidationError

from nirite.campaign.llm.providers import (
    LLMProvider,
    build_analysis_providers
)
from nirite.models.campaign_analysis import CampaignAnalysis

PROMPT_PATH = (
    Path(__file__).parent
    / "llm"
    / "prompts"
    / "campaign_analyser.md"
)

SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")

MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1

def is_server_503(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code == 503:
        return True

    code = getattr(error, "code", None)
    if code == 503 or str(code) == "503":
        return True

    response = getattr(error, "response", None)
    return getattr(response, "status_code", None) == 503

    

class CampaignAnalyser:
    def __init__(
        self,
        providers: list[tuple[str, LLMProvider]] | None = None,
    ) -> None:
        self.providers = (
            providers
            if providers is not None
            else build_analysis_providers()
        )

    def _analyse_with_provider(
        self,
        provider_name: str,
        provider: LLMProvider,
        prompt: str,
    ) -> CampaignAnalysis:
        schema = CampaignAnalysis.model_json_schema()

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                content = provider.generate_json(
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=prompt,
                    schema=schema,
                )
                break
            except Exception as e:
                if not is_server_503(e):
                    raise

                if attempt == MAX_ATTEMPTS:
                    raise RuntimeError(
                        f"Provider '{provider_name}' failed after "
                        f"{MAX_ATTEMPTS} attempts due to 503 errors."
                    ) from e

                time.sleep(RETRY_DELAY_SECONDS * attempt)

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Provider '{provider_name}' returned invalid JSON: {e}"
            ) from e

        try:
            return CampaignAnalysis.model_validate(data)
        except ValidationError as e:
            raise ValueError(
                f"{provider_name} returned invalid campaign analysis: "
                f"{e}"
            ) from e

    def analyse(self, prompt: str) -> list[CampaignAnalysis]:
        if not self.providers:
            raise ValueError("No analysis providers configured.")

        failures: list[str] = []

        # Ministral is the primary analyser; Gemini is the backup used only
        # if Ministral fails. Providers are tried in order; the first one that
        # succeeds returns its analysis. This avoids the latency of running all
        # providers in parallel (bounded by the slowest) while keeping a
        # fallback for when the primary is unavailable or returns invalid output.
        for provider_name, provider in self.providers:
            try:
                analysis = self._analyse_with_provider(
                    provider_name, provider, prompt
                )
                return [analysis]
            except Exception as e:
                failures.append(f"{provider_name}: {e}")
                continue

        raise RuntimeError(
            "Nirite couldn't get a campaign analysis because "
            "one or more AI providers are unavailable. "
            "Please try again later."
            + ("\nProvider errors: " + "; ".join(failures) if failures else "")
        )
