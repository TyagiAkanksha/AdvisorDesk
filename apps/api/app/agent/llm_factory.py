"""Provider selection for the agent LLM (`Settings.llm_provider`)."""

from __future__ import annotations

from typing import Protocol

from app.agent.anthropic_llm import AnthropicAgentLLM
from app.agent.llm import OpenAICompatibleAgentLLM
from app.agent.loop import AgentLLM
from app.config import Settings

__all__ = ["AgentLLMBuilder", "build_agent_llm"]


class AgentLLMBuilder(Protocol):
    """The boot-time instance `app.main` holds: it only mints per-exchange `AgentLLM`s."""

    def new_conversation(self) -> AgentLLM:
        """Return a fresh per-exchange `AgentLLM`."""
        ...


def build_agent_llm(settings: Settings) -> AgentLLMBuilder:
    """Build the boot-time agent LLM for the configured provider."""
    if settings.llm_provider == "anthropic":
        return AnthropicAgentLLM.from_settings(settings)
    return OpenAICompatibleAgentLLM.from_settings(settings)
