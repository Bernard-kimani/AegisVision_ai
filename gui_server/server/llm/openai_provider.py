"""
OpenAI provider stub. Not wired into the provider factory until an API key is
available - exists purely so the interface is proven pluggable now rather than
refactored in later. Implement analyze() the same way gemini_provider.py does
(map ContentPart list -> OpenAI's `content` array shape) when a key exists.
"""

from typing import List

from .base import ContentPart, LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        if not api_key:
            raise ValueError("OpenAI API key not provided")
        self.api_key = api_key
        self.model = model

    def analyze(self, parts: List[ContentPart], max_tokens: int = 1000, temperature: float = 0.3) -> str:
        raise NotImplementedError("OpenAIProvider is not wired up yet - no API key configured for this project.")
