"""`AnthropicChatLLM`: the public-chat `ChatLLM` over the official `anthropic` SDK.

Same contract as `OpenAICompatibleChatLLM` (it reuses that module's prompt builder and error type).
Haiku 5.5 rejects non-default sampling params (HTTP 400), so none are sent;
effort is Settings.llm_effort.

Claude Haiku wrote ~2x longer answers with standalone non-factual sentences that the per-sentence
groundedness judge marks unsupported, so `stream_answer` appends `CLAUDE_STYLE_ADDENDUM` to the
given system text. The OpenAI path is deliberately unchanged.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from typing import Any, cast

import anthropic
import httpx

from app.config import Settings
from app.rag.retrieval import RetrievedChunk
from app.rag.synthesis import ChatCompletionFailedError, _build_user_message

logger = logging.getLogger(__name__)

__all__ = ["CLAUDE_STYLE_ADDENDUM", "AnthropicChatLLM"]

CLAUDE_STYLE_ADDENDUM = " ".join(
    [
        "Style rules for this answer.",
        "Keep it short: at most four sentences.",
        "Every sentence must state a fact taken from the context and end with its citation,"
        " like [1].",
        "Never write a standalone sentence that only says yes or no, announces what comes next,"
        " or bridges between points;",
        "put the yes or no inside the sentence that states the supporting fact, for example"
        " \"The firm's published guidance says yes: shares can be donated the day after they"
        ' vest [1]."',
        "Do not comment on what the sources do or do not contain, unless the context does not"
        " answer the question at all, in which case follow the refusal rule above.",
    ]
)


class AnthropicChatLLM:
    """The real `ChatLLM` for `Settings.llm_provider="anthropic"`."""

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
    def from_settings(cls, settings: Settings) -> AnthropicChatLLM:
        """Build the client; an empty key falls back to `"unset"` so dev boot never crashes."""
        client = anthropic.Anthropic(
            api_key=settings.llm_api_key.get_secret_value() or "unset",
            timeout=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
        )
        return cls(
            client=client,
            model=settings.chat_model,
            max_tokens=settings.llm_max_tokens,
            effort=settings.llm_effort,
        )

    def stream_answer(
        self, system: str, question: str, sources: Sequence[RetrievedChunk]
    ) -> Iterator[str]:
        """Stream the answer as text deltas (`ChatLLM` Protocol).

        Raises:
            ChatCompletionFailedError: any `anthropic.APIError`/`httpx.HTTPError`, opening or
                mid-stream, or a `refusal` stop reason. Provider detail is logged, never put on
                the exception message.
        """
        try:
            with self._client.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                system=f"{system}\n\n{CLAUDE_STYLE_ADDENDUM}",
                messages=[{"role": "user", "content": _build_user_message(question, sources)}],
                output_config=cast(Any, {"effort": self._effort}),
            ) as stream:
                yield from stream.text_stream
                stop_reason = stream.get_final_message().stop_reason
        except (anthropic.APIError, httpx.HTTPError) as exc:
            logger.warning("chat completion provider call failed: %s", exc)
            raise ChatCompletionFailedError("The chat completion provider call failed.") from exc
        if stop_reason == "max_tokens":
            logger.warning("chat completion truncated (stop_reason=max_tokens)")
        if stop_reason == "refusal":
            logger.warning("chat completion refused by provider (stop_reason=refusal)")
            raise ChatCompletionFailedError("The chat completion provider call failed.")
