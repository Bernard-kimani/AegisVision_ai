from .base import ContentPart, LLMProvider
from .gemini_provider import GeminiProvider


def create_provider(provider_name: str, api_key: str, model: str) -> LLMProvider:
    provider_name = (provider_name or "gemini").lower()

    if provider_name == "gemini":
        return GeminiProvider(api_key=api_key, model=model)
    elif provider_name == "openai":
        from .openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=api_key, model=model)
    elif provider_name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=api_key, model=model)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider_name}")


__all__ = ["ContentPart", "LLMProvider", "create_provider"]
