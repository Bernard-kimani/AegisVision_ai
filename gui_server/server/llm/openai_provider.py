"""
OpenAI-compatible provider - speaks the same `/chat/completions` shape used by
OpenAI itself and by the open-weights hosting gateways built on that same API
(Fireworks AI, SiliconFlow, DashScope's OpenAI-compatible mode, etc.), so this
one client is what actually runs Qwen2.5-VL, DeepSeek-V3/R1, or literal GPT
models - whichever `model` + `base_url` you point it at. Nothing else in the
codebase changes: it implements the same `LLMProvider.analyze()` contract as
gemini_provider.py, so vision_compliance.py never knows which vendor answered.

Defaults to Qwen2.5-VL over Fireworks AI's OpenAI-compatible endpoint - it's
the vision-capable open-weights model Agent 2 actually needs (Agent 3 never
calls a model at all). Override via OPENAI_BASE_URL / model if you're pointing
this at a different host or model - confirm the exact model slug against your
provider's current catalog before relying on it live, hosted model names shift.
"""

import logging
import os
from typing import List

import requests

from .base import ContentPart, LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.fireworks.ai/inference/v1"
DEFAULT_MODEL = "accounts/fireworks/models/qwen2p5-vl-32b-instruct"


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, base_url: str = None):
        if not api_key:
            raise ValueError("API key not provided")
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._session = requests.Session()

    def analyze(self, parts: List[ContentPart], max_tokens: int = 1000, temperature: float = 0.3) -> str:
        content = []
        for part in parts:
            if part.kind == "text":
                content.append({"type": "text", "text": part.text})
            elif part.kind == "image_b64":
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{part.mime_type};base64,{part.image_b64}"},
                })
            else:
                raise ValueError(f"Unknown ContentPart kind: {part.kind}")

        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        try:
            response = self._session.post(f"{self.base_url}/chat/completions", json=data, headers=headers, timeout=45)
        except requests.exceptions.RequestException as e:
            logger.error(f"OpenAI-compatible request failed ({self.base_url}): {e}")
            raise

        if response.status_code != 200:
            logger.error(f"OpenAI-compatible API error: {response.status_code} - {response.text}")
            raise Exception(f"OpenAI-compatible API error: {response.status_code}")

        result = response.json()
        choices = result.get("choices") or []
        if not choices:
            logger.error(f"No choices in response: {result}")
            raise Exception("No response choices from provider")

        return choices[0].get("message", {}).get("content", "") or ""
