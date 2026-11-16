"""`AnthropicJudge` — the Claude-backed `GroundednessJudge`/`MetricsJudge`.

Prompts, user-message building and reply parsing are inherited from
`app.eval.groundedness.JudgeBase`; this module owns only the Anthropic wire call. Never sends
`temperature`/`top_p`/`top_k` (rejected by current Claude models); verdict calls use
`output_config.effort`. `anthropic.APIError` propagates unchanged, like `OpenAIJudge`.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import anthropic

from app.config import Settings
from app.eval.groundedness import JudgeBase

__all__ = ["AnthropicJudge"]

logger = logging.getLogger(__name__)


class AnthropicJudge(JudgeBase):
    def __init__(
        self,
        *,
        client: anthropic.Anthropic,
        model: str,
        max_tokens: int = 2048,
        effort: str = "low",
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._effort = effort

    @classmethod
    def from_settings(cls, settings: Settings) -> AnthropicJudge:
        client = anthropic.Anthropic(
            api_key=settings.judge_api_key.get_secret_value() or "unset",
            timeout=settings.embedding_timeout_seconds,
            max_retries=settings.judge_max_retries,
        )
        return cls(
            client=client,
            model=settings.judge_model,
            max_tokens=settings.llm_max_tokens,
            effort=settings.llm_effort,
        )

    def _ask(self, system: str, user: str) -> str:
        """One `messages.create` call; a refusal / no-text reply is an empty string."""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config=cast(Any, {"effort": self._effort}),
        )
        if response.stop_reason == "max_tokens":
            logger.warning("judge reply truncated (stop_reason=max_tokens)")
        if response.stop_reason == "refusal":
            return ""
        text = "".join(block.text for block in response.content if block.type == "text")
        return text.strip()
