"""Answer synthesis: the system prompt, the `ChatLLM` seam, and the real OpenAI-compatible chat
client (PRD §7.5, §7.6, v1.5).

`app.routes.public_routes` depends on `ChatLLM` only — never on `OpenAICompatibleChatLLM`
directly — mirroring `app.rag.embeddings.Embedder`'s seam shape (CONVENTIONS.md §10: external
seams are injectable, never reached in tests). The real client is wired exactly once, in
`app/main.py`.

`dedupe_citations` is the wire (content-level) half of PRD §4's "Citation granularity
(deliberate asymmetry)" — the DB half (chunk-level, `chunk_id` included) lives in
`app.services.chat.record_assistant_message`.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator, Sequence
from typing import Protocol

import httpx
from openai import OpenAI, OpenAIError

from app.config import Settings
from app.rag.retrieval import RetrievedChunk
from app.services.errors import AppError

logger = logging.getLogger(__name__)

__all__ = [
    "SYSTEM_PROMPT",
    "ChatCompletionFailedError",
    "ChatLLM",
    "OpenAICompatibleChatLLM",
    "dedupe_citations",
]


# PRD §7.5 system-prompt intent (verbatim four bullets; wording is explicitly adjustable per the
# PRD note "wording adjustable" — this is that wording):
#   1. Answer ONLY from the provided context chunks.
#   2. Cite with bracketed numbers [1], [2] mapping to the provided sources.
#   3. If the context does not contain the answer: reply that no published guidance covers this,
#      suggest asking the advisory team, and DO NOT answer from general knowledge.
#   4. Never give personalized financial advice; frame answers as "the firm's published guidance
#      says...".
SYSTEM_PROMPT = (
    "You are AdvisorDesk's client-facing assistant. Answer ONLY from the provided context "
    "chunks — never from general knowledge, even if you happen to know the answer. Cite every "
    "claim with bracketed numbers like [1] and [2] that map to the numbered sources listed in "
    "the Context section above the question. If the provided context does not contain the "
    "answer, say plainly that no published guidance covers this, suggest the reader ask the "
    "advisory team, and do not attempt to answer from general knowledge. Never give "
    "personalized financial advice — frame every answer as \"the firm's published guidance "
    'says...", not as advice tailored to the reader.'
)


class ChatLLM(Protocol):
    """The chat-completion seam `app.routes.public_routes` depends on.

    Structurally implemented by `OpenAICompatibleChatLLM` (the real OpenAI-compatible client) and by
    `tests/test_public_chat.py`'s `FakeChatLLM` — a `Protocol`, not an ABC, so a test fake needs
    no inheritance relationship to satisfy it.
    """

    def stream_answer(
        self, system: str, question: str, sources: Sequence[RetrievedChunk]
    ) -> Iterator[str]:
        """Stream the answer to `question`, grounded in `sources`, token by token.

        Args:
            system: the system prompt (`SYSTEM_PROMPT` in production).
            question: the user's message, verbatim.
            sources: the retrieved chunks to ground the answer in, best-similarity-first — empty
                iff PRD §7.4's refusal case (nothing cleared the threshold). Implementations must
                never answer from general knowledge when this is empty (PRD §7.5).

        Yields:
            Successive text fragments of the answer, in order; concatenating every yielded
            fragment reconstructs the full answer text.
        """
        ...


class ChatCompletionFailedError(AppError):
    """The real chat-completion provider call failed (PRD §9) — never surfaces provider detail.

    Raised only by `OpenAICompatibleChatLLM.stream_answer`, always from inside the
    already-streaming `POST /public/chat` response body (`app.routes.public_routes`) — so,
    unlike `EmbeddingFailedError`/`OAuthExchangeError`, it is never registered against an HTTP
    status in `app.routes.errors`: by the time this can be raised, a 200 has already been sent,
    and the only way to report it is the SSE `error` event `app.routes.public_routes` builds
    around any exception `ChatLLM.stream_answer` raises (CONVENTIONS.md §4: "SSE errors use the
    same envelope").
    """

    code = "chat_completion_failed"


def _format_sources(sources: Sequence[RetrievedChunk]) -> str:
    """Render `sources` as the `[n]`-numbered context block `SYSTEM_PROMPT` tells the model to
    cite from. `sources` keeps retrieval's similarity-descending order (PRD §7.3) and is never
    re-sorted here — but `n` is NOT a per-chunk ordinal. `n` is assigned by CONTENT first-use
    order, the exact same rule `dedupe_citations` uses to number the wire citations array: the
    first chunk seen for a given `content_id` fixes that content's number, and every later chunk
    sharing that `content_id` repeats it (phase-4 final review, F1). This is required because the
    model only ever sees this block — it has no way to know a citation's numbering space differs
    from the UI's — so every `[n]` it can legally emit must map 1:1 to `citations[n-1]` on the
    wire (`dedupe_citations(sources)`). Numbering per chunk instead (the pre-fix behavior) let the
    model cite a bracket beyond the deduped array's length, or a bracket that lands on the wrong
    article once two-or-more chunks share a content — live-reproduced in the final review.
    """
    if not sources:
        return "(no context chunks were retrieved for this question)"
    numbers: dict[uuid.UUID, int] = {}
    lines: list[str] = []
    for chunk in sources:
        number = numbers.setdefault(chunk.content_id, len(numbers) + 1)
        lines.append(f"[{number}] {chunk.text}")
    return "\n\n".join(lines)


def _build_user_message(question: str, sources: Sequence[RetrievedChunk]) -> str:
    """Build the single user-turn message: the numbered context block, then the question."""
    return f"Context:\n{_format_sources(sources)}\n\nQuestion: {question}"


class OpenAICompatibleChatLLM:
    """The real `ChatLLM`, built from `Settings` (PRD §7.5, v1.6).

    Talks to an OpenAI-compatible `/v1/chat/completions` endpoint via the `openai` SDK — OpenAI's
    own by default since v1.6 (task 6R-14: the prior NVIDIA NIM chat model went end-of-life),
    NVIDIA NIM's compatible endpoint when `Settings.llm_provider="nvidia"` — mirrors
    `app.rag.embeddings.OpenAICompatibleEmbedder` exactly (`from_settings` classmethod, same
    empty-key-boot-safe `"unset"` fallback via `settings.llm_api_key`), except: `model=settings.
    chat_model`, and streaming via the standard `chat.completions.create(stream=True)` with NO
    provider-specific `extra_body` — the chat-completions path needs neither `input_type` nor
    `truncate`, both embedding-only NIM extras (PRD §7.2 is explicit these are for
    `/v1/embeddings`), so this wire shape is unchanged by the provider swap.
    """

    def __init__(self, *, client: OpenAI, model: str) -> None:
        """Store the already-built SDK client plus the model to answer with.

        Args:
            client: an `openai.OpenAI` client pointed at the provider's OpenAI-compatible base
                URL, already carrying the API key.
            model: the chat-completion model name (`Settings.chat_model`).
        """
        self._client = client
        self._model = model

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAICompatibleChatLLM:
        """Build the real client from `Settings` — the one non-test constructor.

        Mirrors `OpenAICompatibleEmbedder.from_settings` exactly: reads the API key via
        `settings.llm_api_key` (v1.6, task 6R-14) — `openai_api_key` under the default
        `llm_provider="openai"`, else `nvidia_api_key` — and falls back to the harmless
        `"unset"` placeholder when that key is empty (dev-mode boot-safety — the `openai` SDK
        raises at *construction* time for a falsy `api_key` with no `OPENAI_API_KEY`/
        `NVIDIA_API_KEY` env var set either, which would crash `app.main`'s module-level wiring
        on every offline dev boot). Construction stays boot-safe either way; a real chat request
        made with a placeholder key still fails, correctly, as a `ChatCompletionFailedError` at
        request time.

        `timeout=settings.embedding_timeout_seconds` and `max_retries=settings.
        embedding_max_retries` are reused rather than adding dedicated `CHAT_*` settings (task
        brief: "reuse ... or justify a choice in your report") — both budgets exist to bound a
        single provider call/attempt regardless of which OpenAI-compatible endpoint it targets,
        and this client is reused on phase-4's public chat path, where first-token latency
        matters exactly as much as it does for `OpenAICompatibleEmbedder`'s own docstring
        explains for the embedding path. A dedicated `CHAT_TIMEOUT_SECONDS`/`CHAT_MAX_RETRIES`
        pair would be a reasonable follow-up if the two endpoints ever need materially different
        budgets in practice; nothing here forecloses adding one later.
        """
        api_key = settings.llm_api_key.get_secret_value() or "unset"
        client = OpenAI(
            api_key=api_key,
            base_url=settings.llm_base_url,
            timeout=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
        )
        return cls(client=client, model=settings.chat_model)

    def stream_answer(
        self, system: str, question: str, sources: Sequence[RetrievedChunk]
    ) -> Iterator[str]:
        """Stream the model's answer as successive text fragments (`ChatLLM` Protocol).

        Builds exactly two messages — `system` verbatim, then one user turn combining
        `_format_sources(sources)`'s `[n]`-numbered context block with `question` — and streams
        via the standard `chat.completions.create(stream=True)`.

        Raises:
            ChatCompletionFailedError: the provider call failed, either at request time or
                mid-stream (review round 1, finding I-2 — the previous `except OpenAIError` only
                ever caught the former): any `openai.OpenAIError` (auth, rate limit, non-2xx, ...),
                any `httpx.HTTPError` (a connection reset/timeout partway through an already-open
                stream — `httpx.ReadError` is a subclass, probe P15), or a `json.JSONDecodeError`
                from the SDK's own SSE decoder choking on a truncated/malformed chunk (probe P14).
                Deliberately NOT a bare `except Exception` (CONVENTIONS.md §1: "no bare except
                Exception — use the typed family"): these three named types are exactly the
                provider-communication failure family this call can raise; anything else is a real
                bug and should propagate unconverted. The raw provider detail is logged for
                operators, never placed on the exception message (mirrors
                `OpenAICompatibleEmbedder.embed_texts`'s same rule) — `from exc` still chains it
                into the traceback for local debugging.
        """
        try:
            stream = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": _build_user_message(question, sources)},
                ],
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    # A provider can emit a final chunk carrying only usage stats and no
                    # `choices` — nothing to yield, but not an error either.
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except (OpenAIError, httpx.HTTPError, json.JSONDecodeError) as exc:
            # Mirrors `OpenAICompatibleEmbedder.embed_texts`'s M6 rule: the provider's raw
            # exception text (which can carry request/response detail not meant for an end user)
            # is logged for operators, never placed in `ChatCompletionFailedError.message` — the
            # §9 envelope built around this in `app.routes.public_routes` never sees it either.
            logger.warning("chat completion provider call failed: %s", exc)
            raise ChatCompletionFailedError("The chat completion provider call failed.") from exc


def dedupe_citations(chunks: Sequence[RetrievedChunk]) -> list[dict[str, str]]:
    """Dedupe `chunks` to one entry per content item, ordered by first use (PRD §5.3, §4).

    PRD §4 "Citation granularity (deliberate asymmetry)": the public API returns citations
    deduped to content level because the client UI links to articles, not chunks — this is that
    half of the asymmetry (the other half, the chunk-level DB row keeping `chunk_id`, is
    `app.services.chat.record_assistant_message`). "Ordered by first use" (§5.3), not sorted: the
    first chunk seen for a given `content_id` fixes that content's position in the output, even
    when a later, lower-similarity chunk for the SAME content would sort differently by any other
    key (e.g. similarity, or the content's own id) — a plain "collect distinct ids then sort"
    implementation would violate this.

    Args:
        chunks: `RetrievedChunk`s in retrieval order (similarity descending, PRD §7.3).

    Returns:
        One `{"content_id", "title", "slug"}` dict (all values stringified — this is the wire
        shape, JSON-encoded verbatim by `app.routes.sse.sse_event`) per distinct `content_id`, in
        first-occurrence order.
    """
    seen: set[uuid.UUID] = set()
    citations: list[dict[str, str]] = []
    for chunk in chunks:
        if chunk.content_id in seen:
            continue
        seen.add(chunk.content_id)
        citations.append(
            {"content_id": str(chunk.content_id), "title": chunk.title, "slug": chunk.slug}
        )
    return citations
