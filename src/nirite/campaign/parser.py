import json

from openai import OpenAI
from pydantic import ValidationError

from nirite.campaign.models import CampaignDefinition

MODEL = "nvidia/nemotron-3-ultra-550b-a55b"

SYSTEM_PROMPT = """
You turn a user's campaign description into a structured campaign
definition for a lead qualification system.

Return one JSON object matching the supplied JSON schema.
Do not include markdown fences or commentary.

Guidelines:
- Preserve the user's intent. Do not invent requirements.
- Use structured criteria only when a condition can be checked against
  a prospect field using a supported predicate.
- Use semantic criteria for meaning that requires interpretation.
- Use hybrid criteria when both a field check and semantic interpretation
  are useful.
- Requirements are must-haves. Exclusions disqualify. Preferences affect
  ranking but are not hard requirements.
- If essential information is missing or ambiguous, set status to
  "needs_clarification" and include concise clarification questions.
- Generate 3 to 7 distinct search queries covering different useful facets.
  Avoid near-duplicate wording.
- Query plans should improve both discovery coverage and ranking signals.
- Do not claim that appearing in a search result proves qualification.
"""

class CampaignParser:
    def __init__(
        self,
        client: OpenAI,
        model: str = MODEL,
    ) -> None:
        self.client = client
        self.model = model

    def parse(self, prompt: str) -> CampaignDefinition:
        prompt = prompt.strip()
        if not prompt:
           raise ValueError("Campaign description cannot be empty.")

        schema = CampaignDefinition.model_json_schema()

        response = self.client.chat.completions.create(
           model=self.model,
           messages=[
              {
                 "role": "system",
                 "content": (
                    f"{SYSTEM_PROMPT}\n\n"
                    "JSON schema:\n"
                    f"{json.dumps(schema, ensure_ascii=False)}"
                 )
              },
              {
                 "role": "user",
                 "content": prompt
              },
           ],
           # low temperature (0.0-0.3): factual, deterministic, and structured output
           # medium temperature (0.4-0.7): creative, balanced, and exploratory (general-purpose)
           # high temperature (0.8-1.0): imaginative, diverse, and risky (open-ended)
           temperature=0.2,
           max_tokens=8192,
           extra_body={"chat_template_kwargs":{"enable_thinking":True}},
        )

        content = response.choices[0].message.content
        if not content:
           raise ValueError("No content returned from model.")

        # Validate the model's JSON against our Pydantic models.
        try:
           campaign = CampaignDefinition.model_validate_json(content)
        except ValidationError as e:
           raise ValueError(
              f"Model output does not conform to expected schema: {e}"
           ) from e

        campaign.original_prompt = prompt
        return campaign
