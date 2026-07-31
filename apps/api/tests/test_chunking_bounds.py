"""Phase-3 task-01 review rounds 1 (F1/F2/F4/F5) and 2 (lossless `_token_windows` boundaries):
pins the hard chunk-size bound and its companion fixes against pathological markdown that
`tests/test_chunking.py`'s fixtures never exercise (that file is sha256-pinned and stays
untouched -- this is a separate, fresh file).

Round 1's finding: unbounded chunks are not just untidy -- the embedder downstream truncates at
its own token limit, so any chunk content past that point is stored but never vectorized, i.e.
permanently unretrievable. Round 2's finding: round 1's own `_token_windows` fallback, in fixing
that, introduced a *different* content-loss bug -- decoding each token-count-cut window
independently could silently delete a UTF-8 character whose bytes straddled the cut, from both
sides at once. Every test below either measures the exact same pathological shape one of the two
review rounds' live probes hit (an 80-row table, a 50-item tight list, a CRLF document, a single
very long line, a CJK/emoji document, the reviewer's "aé🎉b" straddle case) or a specific
algorithmic defect (`overlap_tokens=0` growth, U+FFFD corruption, tokenizer drift, character
deletion at a token-window boundary).

Fixture technique: reuses the same "vocabulary of near-certainly-single-token common words"
approach as `tests/test_chunking.py` (see that file's module docstring for the full rationale)
so `str.split()` word lists are a faithful proxy for token lists, letting content-conservation
be checked as "input words remain an in-order subsequence of the concatenated chunk text" per
the brief. The CJK/emoji fixtures have no ASCII whitespace at all, so they use exact
whole-string or exact-per-character reconstruction checks instead (round 2's byte-offset fix
makes exactness achievable where round 1 could only claim "most of it survives").
"""

from __future__ import annotations

import tiktoken

from app.rag import chunking
from app.rag.chunking import chunk_markdown, count_tokens

# Same 41-word vocabulary as tests/test_chunking.py -- see that file's module docstring for why
# these particular words (near-certainly single-token, cyclic-position-distinct). Duplicated
# rather than imported so this file's fixtures stand on their own, independent of the pinned
# file's internals.
_VOCAB = [
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "day", "get", "has", "him", "his",
    "how", "man", "new", "now", "old", "see", "two", "way", "who", "boy",
    "did", "its", "let", "put", "say", "she", "too", "use", "run", "top",
    "yes",
]  # fmt: skip


def _word_stream(n: int) -> list[str]:
    """`n` words cycling through `_VOCAB` in a fixed order (matches test_chunking.py)."""
    return [_VOCAB[i % len(_VOCAB)] for i in range(n)]


def _words(text: str) -> list[str]:
    """Whitespace-split word list -- the token-list proxy (matches test_chunking.py)."""
    return text.split()


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    """`True` iff `needle` appears, in order, within `haystack` (extra interleaved elements --
    e.g. markdown table pipes, duplicated overlap words -- don't break the match)."""
    it = iter(haystack)
    return all(any(hay == want for hay in it) for want in needle)


def _paragraphs(*, total_words: int, words_per_paragraph: int) -> str:
    """`total_words` synthetic words, wrapped into blank-line-separated paragraphs."""
    stream = _word_stream(total_words)
    paras = [
        " ".join(stream[i : i + words_per_paragraph])
        for i in range(0, len(stream), words_per_paragraph)
    ]
    return "\n\n".join(paras)


def _assert_bound(
    chunks: list[chunking.ChunkData], target_tokens: int, overlap_tokens: int
) -> None:
    """F1c's invariant: every chunk's `token_count` is `<= target_tokens + overlap_tokens`."""
    ceiling = target_tokens + overlap_tokens
    for chunk in chunks:
        assert chunk.token_count <= ceiling, (
            f"chunk {chunk.chunk_index} has {chunk.token_count} tokens, over the "
            f"target_tokens({target_tokens}) + overlap_tokens({overlap_tokens}) = {ceiling} bound"
        )
        assert chunk.token_count == count_tokens(chunk.text)


# ---------------------------------------------------------------------------
# F1: hard size bound on pathological input shapes.
# ---------------------------------------------------------------------------


def test_wide_markdown_table_stays_within_bound() -> None:
    """F1: an 80-row markdown table has no blank lines between rows, so
    `_PARAGRAPH_SPLIT_RE` treats the whole table as one paragraph unit -- exactly the shape the
    reviewer measured collapsing into one 2178-token chunk. A small `target_tokens` is used
    deliberately to keep the fixture small while still forcing `_split_oversized_unit`'s
    newline-split fallback (the same code path a much larger real table would hit at the
    default target_tokens=400)."""
    stream = _word_stream(80 * 3)
    header = "| " + " | ".join(_VOCAB[:3]) + " |"
    separator = "| --- | --- | --- |"
    rows = ["| " + " | ".join(stream[i : i + 3]) + " |" for i in range(0, len(stream), 3)]
    body = "## Table Section\n\n" + "\n".join([header, separator, *rows])

    chunks = chunk_markdown(body, target_tokens=50, overlap_tokens=10)

    assert len(chunks) > 1
    _assert_bound(chunks, target_tokens=50, overlap_tokens=10)
    assert chunks[0].text.lstrip().startswith("## Table Section")
    haystack = _words(" ".join(c.text for c in chunks))
    assert _is_subsequence(stream, haystack)


def test_tight_list_stays_within_bound() -> None:
    """F1: a 50-item tight (no blank lines between items) list is one giant paragraph unit
    under `_PARAGRAPH_SPLIT_RE`, the shape the reviewer measured collapsing into one
    1202-token chunk."""
    stream = _word_stream(50 * 10)
    items = ["- " + " ".join(stream[i : i + 10]) for i in range(0, len(stream), 10)]
    body = "## List Section\n\n" + "\n".join(items)

    chunks = chunk_markdown(body, target_tokens=50, overlap_tokens=10)

    assert len(chunks) > 1
    _assert_bound(chunks, target_tokens=50, overlap_tokens=10)
    assert chunks[0].text.lstrip().startswith("## List Section")
    haystack = _words(" ".join(c.text for c in chunks))
    assert _is_subsequence(stream, haystack)


def test_crlf_document_normalizes_like_lf_and_stays_within_bound() -> None:
    """F1a: a `\\r\\n` document -- the reviewer measured a whole such document collapsing into
    one 1212-token chunk, because `_PARAGRAPH_SPLIT_RE` (`\\n[ \\t]*\\n`) never matches
    `\\r\\n\\r\\n` (there's a bare `\\r` between the two `\\n`s, not whitespace the regex
    accepts). `chunk_markdown` normalizes line endings up front, so a CRLF document must
    produce results byte-identical to its LF equivalent, not just "some bound-respecting
    output"."""
    body_lf = "## CRLF Section\n\n" + _paragraphs(total_words=300, words_per_paragraph=20)
    body_crlf = body_lf.replace("\n", "\r\n")

    chunks_lf = chunk_markdown(body_lf, target_tokens=50, overlap_tokens=10)
    chunks_crlf = chunk_markdown(body_crlf, target_tokens=50, overlap_tokens=10)

    assert len(chunks_crlf) > 1
    assert chunks_crlf == chunks_lf
    _assert_bound(chunks_crlf, target_tokens=50, overlap_tokens=10)


def test_single_long_line_with_no_newlines_stays_within_bound() -> None:
    """F1b: a single ~300-token paragraph with no newlines or blank lines anywhere (the
    reviewer's "single 600-token paragraph -> 603" case, scaled down) has nothing for
    `_split_oversized_unit`'s newline-split step to find -- it must fall all the way through
    to `_token_windows`' raw token-window slicing."""
    stream = _word_stream(300)
    body = " ".join(stream)

    chunks = chunk_markdown(body, target_tokens=50, overlap_tokens=10)

    assert len(chunks) > 1
    _assert_bound(chunks, target_tokens=50, overlap_tokens=10)
    haystack = _words(" ".join(c.text for c in chunks))
    assert _is_subsequence(stream, haystack)


def test_cjk_paragraph_stays_within_bound_and_uncorrupted() -> None:
    """F1 + F4: a CJK paragraph with no ASCII whitespace at all -- `_split_oversized_unit` finds
    no `\\n` to split on, so this exercises `_token_windows`' raw token-window slicing directly,
    on real multi-byte UTF-8 content (unlike the ASCII-vocabulary fixtures elsewhere in this
    file). Round 2: `_token_windows` slices on byte offsets that only ever move forward to the
    next character boundary, never deleting, so calling it directly (with the exact
    `target_tokens` the end-to-end call below uses internally, via `_split_oversized_unit`) must
    concatenate back to *exactly* the original text -- not "most of it" (round 1's `>= 50%`
    threshold here actually licensed losing half the document, precisely the shape of bug the
    reviewer found). The end-to-end `chunk_markdown` output is checked separately: bound, heading
    survives intact in the first chunk, and no U+FFFD ever appears."""
    cjk_sentence = "这是一段用于测试的中文内容示例文本没有任何空白字符"
    repeats = 30
    body_text = cjk_sentence * repeats
    body = "## CJK Section\n\n" + body_text

    windows = chunking._token_windows(body_text, 50)
    assert "".join(windows) == body_text

    chunks = chunk_markdown(body, target_tokens=50, overlap_tokens=10)

    assert len(chunks) > 1
    _assert_bound(chunks, target_tokens=50, overlap_tokens=10)
    assert chunks[0].text.lstrip().startswith("## CJK Section")
    for chunk in chunks:
        assert "�" not in chunk.text


def test_token_window_straddle_characters_are_never_dropped() -> None:
    """Round 2 (Important): a token-count cut is a cut in the *token* stream, not the *character*
    stream -- a single UTF-8 character's bytes can land in two different tokens. The reviewer's
    example, "aé🎉b", mixes a 1-byte, a 2-byte, and a 4-byte UTF-8 character; sweeping
    `target_tokens` over a wide range against text built from it guarantees at least one value
    lands a cut mid-character. Before this fix, that dropped the straddling character from *both*
    windows (the left window's incomplete tail failed to decode and was silently discarded via
    `errors="ignore"`, the right window's leading continuation bytes were stripped as noise) --
    the reviewer measured 444 of 618 swept (text, target_tokens) combinations losing content this
    way. Every value here must now reconstruct the original text exactly: no loss, no
    duplication (`_token_windows`' windows are non-overlapping by construction)."""
    text = "aé🎉b" * 20 + "测试" * 20

    for target_tokens in range(1, 40):
        windows = chunking._token_windows(text, target_tokens)
        assert "".join(windows) == text, f"target_tokens={target_tokens} corrupted the text"


def test_cjk_emoji_end_to_end_every_distinct_character_survives() -> None:
    """Round 2, end-to-end: a document mixing many distinct CJK and emoji glyphs back-to-back (so
    consecutive characters sit at unpredictable byte offsets relative to any given
    `target_tokens` cut, repeatedly exercising the straddle-sensitive `_token_windows` fallback)
    must surface every distinct input character somewhere in the chunked output -- the
    byte-offset fix makes exact-per-character conservation achievable end-to-end, not just inside
    `_token_windows` itself."""
    glyphs = "测试内容一二三四五六七八九十🎉🎊🎈🎁😀😁😂🤣😃😄"
    body = "## Glyphs\n\n" + glyphs * 15

    chunks = chunk_markdown(body, target_tokens=50, overlap_tokens=10)

    assert len(chunks) > 1
    _assert_bound(chunks, target_tokens=50, overlap_tokens=10)
    reconstructed = "".join(chunk.text for chunk in chunks)
    missing = [glyph for glyph in dict.fromkeys(glyphs) if glyph not in reconstructed]
    assert not missing, f"glyphs missing from every chunk: {missing}"


# ---------------------------------------------------------------------------
# F2: `_tail_tokens(text, 0)` no longer returns the entire text.
# ---------------------------------------------------------------------------


def test_zero_overlap_produces_disjoint_chunks_no_blowup() -> None:
    """F2: `ids[-0:]` is `ids[:]` in Python (the whole list), not zero tokens, so an unguarded
    `_tail_tokens(text, 0)` fed the *entire* previous chunk back in as the next one's seed --
    the reviewer measured 31 exponentially-growing chunks from a 439-token body at
    `overlap_tokens=0`. With `overlap_tokens=0`, chunks must be disjoint: concatenating every
    chunk's words in order must reconstruct the input's word list exactly (no duplication, no
    drift), which is strictly stronger than an approximate token-count check."""
    body = "## Long Section\n\n" + _paragraphs(total_words=450, words_per_paragraph=60)

    chunks = chunk_markdown(body, target_tokens=100, overlap_tokens=0)

    assert len(chunks) > 1
    _assert_bound(chunks, target_tokens=100, overlap_tokens=0)
    reconstructed_words = [word for chunk in chunks for word in _words(chunk.text)]
    assert reconstructed_words == _words(body)


# ---------------------------------------------------------------------------
# F4: overlap slicing never corrupts multi-byte characters.
# ---------------------------------------------------------------------------


def test_emoji_document_has_no_replacement_characters() -> None:
    """F4: `Encoding.decode`'s default `errors="replace"` corrupted an overlap slice that landed
    inside an emoji's multi-byte UTF-8 sequence into a leading U+FFFD -- the reviewer measured
    9 of 10 chunks in an emoji-bearing document starting with the replacement character. A
    small `target_tokens` with the default overlap produces many overlap-seeded chunk
    boundaries, maximizing the chance any surviving corruption would show up."""
    body = "## Emoji Section\n\n" + " ".join(
        f"{_VOCAB[i % len(_VOCAB)]}\U0001f389" for i in range(80)
    )

    chunks = chunk_markdown(body, target_tokens=30, overlap_tokens=10)

    assert len(chunks) > 1
    for chunk in chunks:
        assert "�" not in chunk.text


# ---------------------------------------------------------------------------
# F5: the tokenizer is pinned to cl100k_base (phase-7's harness depends on stable counts).
# ---------------------------------------------------------------------------


def test_tokenizer_is_pinned_to_cl100k_base() -> None:
    """F5: `count_tokens` must agree with `tiktoken.get_encoding("cl100k_base")` exactly, and
    the module must not have quietly switched encodings -- phase-7's groundedness harness
    depends on stable, reproducible token counts across runs and machines."""
    reference = tiktoken.get_encoding("cl100k_base")
    text = "The quick brown fox jumps over the lazy dog. 你好, world! 🎉"

    assert count_tokens(text) == len(reference.encode(text))
    assert chunking._ENCODING_NAME == "cl100k_base"
