"""Pins `app.rag.chunking`'s pure chunking algorithm (PRD §7.1, v1.5: ~400-token target chunks,
50-token overlap) against the phase-3 task-01 brief.

Deliberately DB-less (CONVENTIONS.md §10): `chunk_markdown` is a pure, dependency-light function
with no I/O, so these are plain unit tests — no fixtures beyond synthetic markdown strings, same
spirit as `tests/test_config.py`.

Fixture technique (documented per the task-01 test-author brief, since `tiktoken` is not an
installed dependency yet): the long-section/overlap/token-count fixtures are built from a small
vocabulary of very common, short English words ("the", "and", "for", ...) that are essentially
certain to encode as exactly one `cl100k_base` token each.
`test_vocabulary_is_single_token_per_word` pins that assumption via the module's own
`count_tokens` rather than a hardcoded count, so if the assumption were ever wrong, the failure
points at the fixture, not silently invalidating the overlap assertions. Elsewhere, a "token
list" is the `str.split()` word list of chunk text — the
module exports no `encode` helper (only `count_tokens`, per the brief's Interfaces section), so
whitespace-splitting the controlled single-token vocabulary is the closest available proxy for
tiktoken's own token list, and per-chunk `token_count == count_tokens(text)` checks keep that
proxy honest rather than assumed. The vocabulary is 41 *distinct* words (prime, and coprime with
the default `overlap_tokens=50`) cycled in a fixed order, so a 50-word window's position in the
document is uniquely recoverable from its content — an accidental/incorrect overlap offset cannot
coincidentally produce the same word sequence as the correct one.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.rag.chunking import ChunkData, chunk_markdown, count_tokens

# 41 distinct, very common, short (<=3 letter) English words. High-frequency enough
# to be effectively guaranteed single tokens in `cl100k_base` -- pinned by
# `test_vocabulary_is_single_token_per_word` below rather than assumed silently.
# 41 is prime and > overlap_tokens's factors, so a cyclic window of length >= 41
# uniquely determines its phase (no accidental periodic collisions at the default
# overlap_tokens=50).
_VOCAB = [
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "day", "get", "has", "him", "his",
    "how", "man", "new", "now", "old", "see", "two", "way", "who", "boy",
    "did", "its", "let", "put", "say", "she", "too", "use", "run", "top",
    "yes",
]  # fmt: skip


def _words(text: str) -> list[str]:
    """Whitespace-split word list -- the token-list proxy documented at module level."""
    return text.split()


def _word_stream(n: int) -> list[str]:
    """`n` words cycling through `_VOCAB` in a fixed order (deterministic, position-distinct)."""
    return [_VOCAB[i % len(_VOCAB)] for i in range(n)]


def _paragraphs(*, total_words: int, words_per_paragraph: int) -> str:
    """`total_words` synthetic words, wrapped into blank-line-separated paragraphs."""
    stream = _word_stream(total_words)
    paras = [
        " ".join(stream[i : i + words_per_paragraph])
        for i in range(0, len(stream), words_per_paragraph)
    ]
    return "\n\n".join(paras)


def test_vocabulary_is_single_token_per_word() -> None:
    """Fixture sanity pin: every `_VOCAB` word must be exactly one `cl100k_base` token.

    If this ever fails, swap the offending word(s) out of `_VOCAB` -- the
    long-section/overlap/token-count tests below depend on 1 word == 1 token to
    treat `str.split()` output as a faithful token-list proxy.
    """
    for word in _VOCAB:
        assert count_tokens(word) == 1, f"{word!r} is not a single token"


def test_heading_split_two_sections_under_target() -> None:
    """PRD §7.1: two `## `-headed sections, each well under 400 tokens, become 2 chunks with
    boundaries exactly at the headings and contiguous 0-based indices."""
    body = (
        "## Section One\n\n"
        + " ".join(_word_stream(20))
        + "\n\n## Section Two\n\n"
        + " ".join(_word_stream(25))
    )

    chunks = chunk_markdown(body)

    assert [c.chunk_index for c in chunks] == [0, 1]
    assert chunks[0].text.lstrip().startswith("## Section One")
    assert chunks[1].text.lstrip().startswith("## Section Two")
    assert "Section Two" not in chunks[0].text
    assert "Section One" not in chunks[1].text


def test_order_and_indices_preserve_document_order_not_sorted() -> None:
    """Multiple headed sections come back in document order with contiguous 0-based indices.

    Headings are deliberately non-alphabetical (Zebra, Apple, Mango) so an
    accidental sort-by-heading-text bug would be caught rather than passing by
    coincidence.
    """
    body = (
        "## Zebra Topic\n\n"
        + " ".join(_word_stream(15))
        + "\n\n## Apple Topic\n\n"
        + " ".join(_word_stream(15))
        + "\n\n## Mango Topic\n\n"
        + " ".join(_word_stream(15))
    )

    chunks = chunk_markdown(body)

    assert [c.chunk_index for c in chunks] == [0, 1, 2]
    assert chunks[0].text.lstrip().startswith("## Zebra Topic")
    assert chunks[1].text.lstrip().startswith("## Apple Topic")
    assert chunks[2].text.lstrip().startswith("## Mango Topic")


def test_long_section_splits_within_token_ceiling_and_overlaps() -> None:
    """PRD §7.1: a section far over 400 tokens splits on paragraph boundaries into chunks each
    <= ~450 tokens (target + overlap headroom), with the first `overlap_tokens` (default 50)
    tokens of chunk N+1 appearing at the tail of chunk N."""
    body = "## Long Section\n\n" + _paragraphs(total_words=1200, words_per_paragraph=60)

    chunks = chunk_markdown(body)

    assert len(chunks) >= 3
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    for chunk in chunks:
        assert chunk.token_count <= 450
        assert chunk.token_count == count_tokens(chunk.text)

    for prev_chunk, next_chunk in zip(chunks, chunks[1:], strict=False):
        prev_tail = _words(prev_chunk.text)[-50:]
        next_head = _words(next_chunk.text)[:50]
        assert len(prev_tail) == 50
        assert len(next_head) == 50
        assert prev_tail == next_head


def test_short_doc_single_paragraph_is_one_chunk() -> None:
    """A body with no headings, well under the token target, is exactly one chunk at index 0."""
    body = " ".join(_word_stream(30))

    chunks = chunk_markdown(body)

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert _words(chunks[0].text) == _words(body)


@pytest.mark.parametrize("body", ["", "   ", "\n\n\t  \n"])
def test_empty_or_whitespace_body_returns_no_chunks(body: str) -> None:
    """PRD §7.1: empty/whitespace body -> `[]`, never a single empty chunk."""
    assert chunk_markdown(body) == []


def test_determinism_two_calls_produce_equal_results() -> None:
    """Same input -> equal `ChunkData` list across calls -- no hidden nondeterminism (dict/set
    iteration order, random ids, wall-clock, etc.)."""
    body = "## Long Section\n\n" + _paragraphs(total_words=900, words_per_paragraph=60)

    first = chunk_markdown(body)
    second = chunk_markdown(body)

    assert len(first) > 1
    assert first == second


def test_chunk_data_is_frozen_with_expected_fields() -> None:
    """`ChunkData` is a frozen dataclass with exactly `text`/`chunk_index`/`token_count` -- later
    tasks (task-02 lifecycle, phase-7 groundedness harness) rely on this exact shape."""
    field_names = {f.name for f in dataclasses.fields(ChunkData)}
    assert field_names == {"text", "chunk_index", "token_count"}

    chunk = ChunkData(text="hello world", chunk_index=0, token_count=count_tokens("hello world"))

    with pytest.raises(dataclasses.FrozenInstanceError):
        chunk.chunk_index = 1  # type: ignore[misc]


def test_chunk_data_token_count_agrees_with_count_tokens() -> None:
    """Every chunk `chunk_markdown` returns has `token_count == count_tokens(text)` -- the field
    must never drift from the tokenizer it is derived from."""
    body = (
        "## Section One\n\n"
        + " ".join(_word_stream(20))
        + "\n\n## Section Two\n\n"
        + " ".join(_word_stream(600))
    )

    chunks = chunk_markdown(body)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.token_count == count_tokens(chunk.text)
