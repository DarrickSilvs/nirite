import os
import json
from typing import Protocol

from dotenv import load_dotenv
from litellm import completion

load_dotenv()

OPENROUTER_MODEL = "openrouter/mistralai/ministral-3b-2512"
GEMINI_MODEL = "gemini/gemini-3.1-flash-lite"
NVIDIA_ANALYSIS_MODEL = "nvidia_nim/nvidia/nemotron-3.5-bolt-e4b"
NVIDIA_PARSER_MODEL = "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

REQUEST_TIMEOUT = 180.0

class LLMProvider(Protocol):
    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,  
        schema: dict,
    ) -> str:
        ...

class LiteLLMProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        api_base: str | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.api_base = api_base

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict,
    ) -> str:
        schema_instruction = (
            "\n\nYour response must conform to this JSON schema:\n"
            f"{json.dumps(schema, indent=2)}"
        )

        response = completion(
            model=self.model,
            api_key=self.api_key,
            api_base=self.api_base,
            messages=[
                {
                    "role": "system",
                    "content": f"{system_prompt}{schema_instruction}",
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
            timeout=REQUEST_TIMEOUT,
        )

        if not response.choices:
            raise RuntimeError(f"{self.model} returned no choices.")

        content = response.choices[0].message.content

        if not content:
            raise RuntimeError(f"{self.model} returned no content.")

        return content
    
def get_api_key(env_name: str) -> str:
    api_key = os.getenv(env_name)
    if not api_key:
        raise RuntimeError(f"{env_name} missing. Add to root .env file.")
    return api_key

def build_analysis_providers() -> list[tuple[str, LLMProvider]]:
    mistral = LiteLLMProvider(
        api_key=get_api_key("MISTRAL_OPENROUTER_API_KEY"),
        model=OPENROUTER_MODEL,
    )

    gemini = LiteLLMProvider(
        api_key=get_api_key("GEMINI_FLASH_LITE_API_KEY"),
        model=GEMINI_MODEL,
    )

    nemotron = LiteLLMProvider(
        api_key=get_api_key("NVIDIA_BOLT_E4B_API_KEY"),
        model=NVIDIA_ANALYSIS_MODEL,
    )

    return [
        ("Ministral", mistral),
        ("Gemini", gemini),
        ("Nemotron", nemotron),
    ]

def build_parser_provider() -> LLMProvider:
    return LiteLLMProvider(
        api_key=get_api_key("NVIDIA_550B_API_KEY"),
        model=NVIDIA_PARSER_MODEL,
    )