"""
Gemini provider - adapted from the old trading_server.py's GeminiClient, but
speaking the vendor-neutral ContentPart list instead of a single (text, image) pair.

Disables "thinking" by default (thinkingConfig.thinkingBudget=0): benchmarked at
~1.5s round-trip vs. a call that silently burns its entire max_tokens budget on
internal reasoning and returns empty text (MAX_TOKENS finish reason, no visible
output) - this matters directly for the sub-7s latency target.
"""

import logging
from typing import List, Optional

import requests

from .base import ContentPart, LLMProvider

logger = logging.getLogger(__name__)

GEMINI_MODEL_ALIASES = {
    "gemini-1.5-flash": "gemini-1.5-flash-latest",
    "gemini-1.5-pro": "gemini-1.5-pro-latest",
}


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", disable_thinking: bool = True):
        if not api_key:
            raise ValueError("Gemini API key not provided")
        self.api_key = api_key
        self.model = model
        self.disable_thinking = disable_thinking

    def analyze(self, parts: List[ContentPart], max_tokens: int = 1000, temperature: float = 0.3) -> str:
        model_name = GEMINI_MODEL_ALIASES.get(self.model, self.model)

        gemini_parts = []
        for part in parts:
            if part.kind == "text":
                gemini_parts.append({"text": part.text})
            elif part.kind == "image_b64":
                gemini_parts.append({"inline_data": {"mime_type": part.mime_type, "data": part.image_b64}})
            else:
                raise ValueError(f"Unknown ContentPart kind: {part.kind}")

        generation_config = {
            "temperature": float(temperature),
            "maxOutputTokens": int(max_tokens),
        }
        if self.disable_thinking:
            generation_config["thinkingConfig"] = {"thinkingBudget": 0}

        data = {
            "contents": [{"parts": gemini_parts}],
            "generationConfig": generation_config,
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"

        try:
            response = requests.post(url, json=data, timeout=45)
        except requests.exceptions.RequestException as e:
            logger.error(f"Gemini request failed: {e}")
            raise

        if response.status_code != 200:
            logger.error(f"Gemini API error: {response.status_code} - {response.text}")
            raise Exception(f"Gemini API error: {response.status_code}")

        result = response.json()
        candidates = result.get("candidates") or []
        if not candidates:
            logger.error(f"No candidates in Gemini response: {result}")
            raise Exception("No response candidates from Gemini")

        candidate = candidates[0]
        content_parts = candidate.get("content", {}).get("parts", [])
        if not content_parts:
            finish_reason = candidate.get("finishReason", "UNKNOWN")
            logger.error(f"Gemini returned no text parts (finishReason={finish_reason}): {candidate}")
            raise Exception(f"Empty Gemini response (finishReason={finish_reason})")

        return content_parts[0].get("text", "")
