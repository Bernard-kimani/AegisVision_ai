"""
Pluggable LLM provider interface.

vision_compliance.py builds a list of ContentPart (text/image) and calls
analyze() - it never talks to a specific vendor's API shape directly. Adding
Claude or OpenAI as a fallback later means implementing this interface, not
touching the agent that consumes it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ContentPart:
    kind: str  # "text" | "image_b64"
    text: Optional[str] = None
    image_b64: Optional[str] = None
    mime_type: str = "image/png"

    @staticmethod
    def text_part(text: str) -> "ContentPart":
        return ContentPart(kind="text", text=text)

    @staticmethod
    def image_part(image_b64: str, mime_type: str = "image/png") -> "ContentPart":
        return ContentPart(kind="image_b64", image_b64=image_b64, mime_type=mime_type)


class LLMProvider(ABC):
    """A multimodal chat-completion provider."""

    @abstractmethod
    def analyze(self, parts: List[ContentPart], max_tokens: int = 1000, temperature: float = 0.3) -> str:
        """Send ordered text/image parts to the model, return the raw text response."""
