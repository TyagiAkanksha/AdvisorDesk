"""Provider selection for the public-chat LLM (`Settings.llm_provider`)."""

from __future__ import annotations

from app.config import Settings
from app.rag.anthropic_chat import AnthropicChatLLM
from app.rag.synthesis import ChatLLM, OpenAICompatibleChatLLM

__all__ = ["build_chat_llm"]


def build_chat_llm(settings: Settings) -> ChatLLM:
    """Build the chat LLM for the configured provider."""
    if settings.llm_provider == "anthropic":
        return AnthropicChatLLM.from_settings(settings)
    return OpenAICompatibleChatLLM.from_settings(settings)
