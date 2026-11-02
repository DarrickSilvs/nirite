import json
from pathlib import Path

from pydantic import ValidationError

from nirite.campaign.llm.providers import LLMProvider
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
class CampaignParser:
   def __init__(self, provider: LLMProvider) -> None:
      self.provider = provider

   def parse(
         self, 
         prompt: str, 
         analyses: list[CampaignAnalysis]
   ) -> CampaignDefinition:
      
      prompt = prompt.strip()
      if not prompt:
         raise ValueError("Campaign description cannot be empty.")

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

      content = self.provider.generate_json(
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

         content = self.provider.generate_json(
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
         campaign = CampaignDefinition.model_validate(data)
      except ValidationError as e:
         raise ValueError(
            f"Model output does not conform to expected schema: {e}"
         ) from e

      campaign.original_prompt = prompt
      return campaign
