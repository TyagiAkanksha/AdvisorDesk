"""Fix-wave pin for F1 (phase-4 whole-branch final review,
`.superpowers/sdd/reports/p4-final-review.md`): the citation-numbering seam between
`app.rag.synthesis._format_sources` (the prompt's `[n]`-numbered context block, what the model
reads and cites from) and `app.rag.synthesis.dedupe_citations` (the wire citations array the UI
numbers its chips from).

Before this fix wave, `_format_sources` numbered `[1..k]` per CHUNK (similarity order), while
`dedupe_citations` numbers `[1..m]` per DEDUPED CONTENT (first-use order) — two different
numbering spaces sharing the same bracket syntax. The live repro in the final review report
(`p4-final-review.md`, finding F1) showed a model citing `[2]` under the old per-chunk numbering
landing on the WRONG UI chip once a retrieval spanned multiple chunks per content — the common
case, since `retrieve()` returns up to 6 chunks over as few as 1-3 distinct articles.

This file is new (CONVENTIONS.md §10 unique-test-file-basename rule); it exercises
`_format_sources` and `dedupe_citations` directly, unit-level, with a hand-built
`RetrievedChunk` sequence — no DB needed (both functions are pure over `Sequence[RetrievedChunk]`).
"""

from __future__ import annotations

import re
import uuid

from app.rag.retrieval import RetrievedChunk
from app.rag.synthesis import _format_sources, dedupe_citations

_SOURCE_LINE = re.compile(r"^\[(\d+)\] (.*)$", re.DOTALL)


def _chunk(
    *, content_id: uuid.UUID, title: str, slug: str, text: str, similarity: float = 0.9
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        content_id=content_id,
        title=title,
        slug=slug,
        text=text,
        similarity=similarity,
    )


def test_format_sources_numbers_by_content_first_use_matching_dedupe_citations() -> None:
    """Scripted retrieval mirroring the live repro: 3 chunks over 2 contents, with the
    shared-content chunk NOT adjacent to its sibling (content A at retrieval positions 0 and 2,
    content B at position 1 — the exact non-adjacent shape that exposed the bug, since a naive
    per-chunk scheme numbers position-0 and position-2 differently even though they're the same
    article).

    The invariant pinned here (F1's fix contract, not a specific implementation choice): the set
    of `[n]` values a model can legally emit from the prompt's source block is EXACTLY
    `{1, ..., len(dedupe_citations(sources))}`, in the same order — i.e. `max(source numbers) ==
    len(citations)`, and each source number `n`'s underlying content matches `citations[n-1]`'s
    slug.
    """
    content_a = uuid.uuid4()
    content_b = uuid.uuid4()
    chunks = (
        _chunk(content_id=content_a, title="Article A", slug="article-a", text="A first chunk."),
        _chunk(content_id=content_b, title="Article B", slug="article-b", text="B only chunk."),
        _chunk(content_id=content_a, title="Article A", slug="article-a", text="A second chunk."),
    )

    prompt_block = _format_sources(chunks)
    citations = dedupe_citations(chunks)

    # dedupe_citations: content first-use order -> [A, B] (§5.3, §4 of the PRD).
    assert [c["slug"] for c in citations] == ["article-a", "article-b"]

    # Exact pin of the fix's chosen shape: shared bracket number for chunks of the same content,
    # numbered by first-use order — content A's non-adjacent second chunk repeats "[1]", NOT "[3]".
    assert prompt_block == ("[1] A first chunk.\n\n[2] B only chunk.\n\n[1] A second chunk.")

    # General invariant (would catch any other valid numbering scheme too, not just this exact
    # string): every `[n]` in the prompt maps 1:1 onto `citations[n-1]`.
    blocks = prompt_block.split("\n\n")
    parsed = []
    for block in blocks:
        match = _SOURCE_LINE.match(block)
        assert match is not None, f"source block line has no leading [n]: {block!r}"
        parsed.append((int(match.group(1)), match.group(2)))

    max_source_number = max(number for number, _ in parsed)
    assert max_source_number == len(citations)

    text_to_slug = {chunk.text: chunk.slug for chunk in chunks}
    for number, text in parsed:
        assert text_to_slug[text] == citations[number - 1]["slug"]


def test_format_sources_single_chunk_per_content_numbers_sequentially() -> None:
    """The common single-chunk-per-content case (and the shape `test_chat_llm_client.py`'s pinned
    `"[1] Roth IRAs grow tax-free."` assertion exercises) is unaffected: with no shared
    `content_id`, content-first-use numbering and per-chunk numbering coincide.
    """
    chunks = (
        _chunk(content_id=uuid.uuid4(), title="A", slug="a", text="first."),
        _chunk(content_id=uuid.uuid4(), title="B", slug="b", text="second."),
        _chunk(content_id=uuid.uuid4(), title="C", slug="c", text="third."),
    )

    prompt_block = _format_sources(chunks)
    citations = dedupe_citations(chunks)

    assert prompt_block == "[1] first.\n\n[2] second.\n\n[3] third."
    assert len(citations) == 3


def test_format_sources_empty_sources_still_renders_the_placeholder() -> None:
    """Zero sources (PRD §7.4/§7.5 refusal path) is untouched by the numbering fix."""
    assert _format_sources(()) == "(no context chunks were retrieved for this question)"
    assert dedupe_citations(()) == []
