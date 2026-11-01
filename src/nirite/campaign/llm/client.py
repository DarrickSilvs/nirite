import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

def create_client() -> OpenAI:
    api_key = os.getenv("NVIDIA_API_KEY")

    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY missing. Add to root .env file.")

    return OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key
    )
    
    