import json
from pathlib import Path

from pydantic import ValidationError

from nirite.campaign.llm.providers import LLMProvider
from nirite.campaign.llm.providers import build_parser_provider
from nirite.models.campaign import CampaignDefinition
from nirite.models.campaign_analysis import CampaignAnalysis


PROMPT_PATH = Path(__file__).parent / "llm" / "prompts" / "campaign_parser.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


def parse_json(content: str) -> dict:
    if not content:
        raise ValueError("No content returned from model.")

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Model returned invalid JSON: {e}") from e


def assign_stable_ids(data: dict) -> dict:
    """Replace model-chosen IDs with c1..cn / q1..qn and remap references.

    Runs before validation so ID style never varies between runs. Malformed
    shapes are left untouched for schema validation to report.
    """
    spec = data.get("spec")
    plan = data.get("query_plan")
    mapping: dict[str, str] = {}

    if isinstance(spec, dict) and isinstance(spec.get("criteria"), list):
        for index, criterion in enumerate(spec["criteria"], start=1):
            if not isinstance(criterion, dict):
                continue
            new_id = f"c{index}"
            mapping.setdefault(str(criterion.get("id")), new_id)
            criterion["id"] = new_id

    if isinstance(plan, dict) and isinstance(plan.get("queries"), list):
        for index, query in enumerate(plan["queries"], start=1):
            if isinstance(query, dict):
                query["id"] = f"q{index}"

    clarifications = data.get("clarifications")
    if isinstance(clarifications, list):
        for clarification in clarifications:
            refs = (
                clarification.get("related_criterion_ids")
                if isinstance(clarification, dict)
                else None
            )
            if isinstance(refs, list):
                # unknown references are kept so validation rejects them
                clarification["related_criterion_ids"] = [
                    mapping.get(str(ref), ref) for ref in refs
                ]

    return data


class CampaignParser:
    def __init__(
        self,
        providers: list[tuple[str, LLMProvider]] | None = None,
    ) -> None:
        self.providers = (
            providers
            if providers is not None
            else build_parser_provider()
        )

    def _parse_with_provider(
        self,
        provider_name: str,
        provider: LLMProvider,
        prompt: str,
        analyses: list[CampaignAnalysis],
    ) -> CampaignDefinition:
        schema = CampaignDefinition.model_json_schema()

        user_message = f"""
           Original campaign description:

           {prompt}

           Independent campaign analyses:

           {json.dumps(
              [analysis.model_dump(mode="json") for analysis in analyses],
              indent=2,
           )}

           Generate the final CampaignDefinition using the original description
           and the independent analyses.
           """

        content = provider.generate_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_message,
            schema=schema,
        )

        if not content:
            raise ValueError("No content returned from model.")

        try:
            data = parse_json(content)
        except ValueError as first_error:
            if "No content returned" in str(first_error):
                raise

            retry_user_message = (
                f"{user_message}\n\n"
                f"Your previous response was not valid JSON:\n{content}\n\n"
                "Return the same campaign definition as one complete JSON object "
                "matching the supplied schema. Do not change its interpretation "
                "or add commentary."
            )

            content = provider.generate_json(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=retry_user_message,
                schema=schema,
            )
            try:
                data = parse_json(content)
            except ValueError as second_error:
                raise ValueError(
                   "Model returned invalid JSON after one retry. "
                   f"error={second_error}"
                ) from second_error

        try:
            campaign = CampaignDefinition.model_validate(assign_stable_ids(data))
        except ValidationError as first_error:
            retry_user_message = (
                f"{user_message}\n\n"
                "Your previous response was valid JSON but did not match "
                "the required CampaignDefinition schema.\n"
                "Correct its structure using the supplied schema. Preserve "
                "the campaign's interpretation and values. Return one complete "
                "JSON object only.\n\n"
                f"Validation error:\n{first_error}\n\n"
                f"Previous response:\n{content}"
            )

            content = provider.generate_json(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=retry_user_message,
                schema=schema,
            )

            try:
                data = parse_json(content)
                campaign = CampaignDefinition.model_validate(assign_stable_ids(data))
            except (ValueError, ValidationError) as second_error:
                raise ValueError(
                   "Model output did not conform to the schema after one retry. "
                   f"{second_error}"
                ) from second_error

        campaign.original_prompt = prompt
        return campaign

    def parse(self, prompt: str, analyses: list[CampaignAnalysis]) -> CampaignDefinition:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Campaign description cannot be empty.")

        if not self.providers:
            raise ValueError("No parsing providers configured.")

        failures: list[str] = []

        # Gemini is the primary parser; Ministral is the backup used only
        # if Gemini fails. Providers are tried in order; the first one that
        # succeeds returns its result.
        for provider_name, provider in self.providers:
            try:
                return self._parse_with_provider(
                    provider_name, provider, prompt, analyses
                )
            except Exception as e:
                failures.append(f"{provider_name}: {e}")
                continue

        raise RuntimeError(
            "Nirite couldn't parse the campaign because "
            "one or more AI providers are unavailable. "
            "Please try again later."
            + ("\nProvider errors: " + "; ".join(failures) if failures else "")
        )
