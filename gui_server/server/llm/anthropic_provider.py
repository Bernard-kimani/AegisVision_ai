"""
Anthropic (Claude) provider stub - the spec's intended secondary/fallback vision
model. Not wired into the provider factory until an API key is available. See
openai_provider.py's note; implement analyze() by mapping ContentPart -> Claude's
content-block shape (image blocks before text, per Claude's recommended ordering)
when a key exists.
"""

from typing import List

from .base import ContentPart, LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        if not api_key:
            raise ValueError("Anthropic API key not provided")
        self.api_key = api_key
        self.model = model

    def analyze(self, parts: List[ContentPart], max_tokens: int = 1000, temperature: float = 0.3) -> str:
        raise NotImplementedError("AnthropicProvider is not wired up yet - no API key configured for this project.")
