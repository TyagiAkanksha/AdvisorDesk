"""Deterministic markdown chunking for the RAG pipeline (PRD §7.1, v1.5).

Pure, dependency-light, and leaf-clean: no application I/O; the tokenizer loads
its BPE table once per process (pre-warmed in the image — see
`infra/Dockerfile.api`'s `TIKTOKEN_CACHE_DIR` layer — so even that one-time load
never touches the network at runtime). No imports from any other `app.*`
package (CONVENTIONS.md §2 `rag/` layer; this module in particular has no reason
to reach into `services`/`models`/`config`, so it stays a true leaf even though
the layer as a whole is permitted to). `chunk_markdown` is called both by the
publish/re-embed lifecycle pipeline (phase-3 task-02) and the groundedness
evaluation harness (phase 7), so its output shape (`ChunkData`) and ordering
guarantees are a stable contract for both callers.

Tokenizer choice: `tiktoken`'s `cl100k_base` encoding. The PRD says "tokens"
without naming a tokenizer (§7.1); `cl100k_base` is used purely as a consistent,
deterministic proxy for chunk sizing — it is not the embedding model's own
tokenizer (`nvidia/nv-embedqa-e5-v5`, an NVIDIA NIM model, does not publish a
`tiktoken` encoding). See the README's "Implementation notes" section for the
short version of this note.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import tiktoken

# ATX headings only (`#` through `######` followed by a space), at the start of
# a line -- PRD §7.1 "split `body_md` by markdown headings".
_HEADING_RE = re.compile(r"^#{1,6} .*$", re.MULTILINE)

# Markdown paragraph boundary: a blank line (optionally containing whitespace).
_PARAGRAPH_SPLIT_RE = re.compile(r"\n[ \t]*\n")

_ENCODING_NAME = "cl100k_base"


@dataclass(frozen=True)
class ChunkData:
    """One retrieval-ready slice of a content item's `body_md` (PRD §7.1).

    Produced by `chunk_markdown`; consumed by the publish/re-embed lifecycle
    (phase-3 task-02, which persists these as `Chunk` rows) and the phase-7
    groundedness harness. The field set and types are a contract other tasks
    depend on verbatim -- do not rename or add required fields without
    updating both callers.
    """

    text: str
    chunk_index: int
    token_count: int


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    """Return the process-wide `cl100k_base` encoding, loaded once.

    `tiktoken.get_encoding` re-parses its BPE rank file on every call; caching
    the single `Encoding` instance avoids paying that cost per `count_tokens`
    call (called at least once per chunk, often more, in `chunk_markdown`).
    """
    return tiktoken.get_encoding(_ENCODING_NAME)


def count_tokens(text: str) -> int:
    """Return the number of `cl100k_base` tokens `text` encodes to.

    Args:
        text: arbitrary text (markdown or plain).

    Returns:
        Token count under the `cl100k_base` encoding (see module docstring
        for why this tokenizer, specifically, was chosen).
    """
    return len(_encoding().encode(text))


def chunk_markdown(
    body_md: str,
    *,
    target_tokens: int = 400,
    overlap_tokens: int = 50,
) -> list[ChunkData]:
    """Split `body_md` into ordered, token-bounded chunks (PRD §7.1, v1.5).

    Algorithm (pinned by `tests/test_chunking.py`, not just this docstring):
    line endings are normalized to `\\n` first (F1a: a `\\r\\n`/`\\r` document
    would otherwise fail to match either the blank-line paragraph regex or, in
    principle, the heading regex, since both are anchored on `\\n`); the body
    is then split on markdown headings (`^#{1,6} `) into sections; a section
    that fits within `target_tokens` is packed whole into a single chunk
    (never merged with a neighboring section -- every heading is always a
    chunk boundary); a section longer than `target_tokens` is split on
    paragraph boundaries (blank lines), packing whole paragraphs up to
    `target_tokens` per chunk, with the trailing `overlap_tokens` tokens of
    each chunk repeated as the leading tokens of the next chunk from the same
    section. A single paragraph that alone exceeds `target_tokens` (a giant
    markdown table, a tight list with no blank lines between items, one
    unbroken run of text) is split further rather than emitted whole (F1b) --
    see `_split_oversized_unit`. `chunk_index` is 0-based document order. An
    empty or whitespace-only body returns `[]`.

    Invariant (F1c, enforced by construction and tested by
    `tests/test_chunking_bounds.py`): every returned chunk's `token_count` is
    `<= target_tokens + overlap_tokens`. Unbounded chunks are not just an
    aesthetic problem -- the embedder downstream truncates at its own token
    limit, so any content past that point is stored but never vectorized
    (permanently unretrievable).

    Args:
        body_md: the content item's markdown body.
        target_tokens: soft per-chunk token budget (PRD §7.1 default: 400).
        overlap_tokens: trailing/leading token overlap between adjacent
            chunks produced by splitting one long section (default: 50).

    Returns:
        `ChunkData` instances in document order, `chunk_index` 0-based and
        contiguous. `[]` for an empty/whitespace-only `body_md`.
    """
    body_md = body_md.replace("\r\n", "\n").replace("\r", "\n")
    if not body_md.strip():
        return []

    texts: list[str] = []
    for section in _split_sections(body_md):
        if not section.strip():
            continue
        if count_tokens(section) <= target_tokens:
            texts.append(section)
        else:
            texts.extend(_split_long_section(section, target_tokens, overlap_tokens))

    return [
        ChunkData(text=text, chunk_index=index, token_count=count_tokens(text))
        for index, text in enumerate(texts)
    ]


def _split_sections(body_md: str) -> list[str]:
    """Split `body_md` on ATX heading lines, each section keeping its heading.

    Any content before the first heading (or the whole body, if there is no
    heading at all) is its own leading section. A heading always starts a new
    section that runs up to -- but not including -- the next heading.
    """
    headings = list(_HEADING_RE.finditer(body_md))
    if not headings:
        return [body_md]

    sections: list[str] = []
    preamble = body_md[: headings[0].start()]
    if preamble.strip():
        sections.append(preamble)

    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body_md)
        sections.append(body_md[heading.start() : end])

    return sections


def _split_long_section(section: str, target_tokens: int, overlap_tokens: int) -> list[str]:
    """Split one over-budget section into paragraph-packed, overlapping chunks.

    Paragraphs (blank-line-separated units, the section's heading line counts
    as its own leading unit) are packed greedily into a chunk while it stays
    within `target_tokens`; at least one unit is always added per chunk so
    progress is guaranteed. Each subsequent chunk is seeded with the exact
    trailing `overlap_tokens` tokens of the previous chunk's text (via
    `_tail_tokens`) so the overlap is a verbatim substring, not a
    reconstruction that could drift from the original wording.

    A paragraph that alone exceeds `target_tokens` (F1b's hard fallback -- an
    80-row table, a 50-item tight list, one 2000-token line with no newlines
    at all) is pre-split via `_split_oversized_unit` into smaller pieces
    *before* packing, so every unit the packing loop below actually sees is
    individually `<= target_tokens`. Because this pre-split happens as a
    single flat pass over the whole section, a heading (the section's leading
    unit) is packed together with however many units of its section's first
    chunk fit -- never flushed alone as an orphan-heading chunk, even when
    the very next paragraph needed the hard fallback.

    Packing decisions use the *real*, freshly recomputed token count of the
    joined-so-far text, not a sum of each part's independently-counted
    tokens: the `"\\n\\n"` separator itself costs tokens, and BPE can
    retokenize slightly differently right at a join boundary, so the sum
    estimate can undercount the true joined size by a token or two. That
    slack is invisible against a 400-token target packed from ~60-token
    paragraphs (comfortable headroom either way), but becomes the whole
    story when an atom is already sitting at exactly `target_tokens` (as
    every non-final `_token_windows` atom is, by construction) -- estimating
    there would silently let the emitted chunk exceed the F1c bound.
    """
    units = [unit for unit in _PARAGRAPH_SPLIT_RE.split(section) if unit.strip()]
    if not units:
        return []

    atoms: list[str] = []
    for unit in units:
        if count_tokens(unit) > target_tokens:
            atoms.extend(_split_oversized_unit(unit, target_tokens))
        else:
            atoms.append(unit)

    chunks: list[str] = []
    prefix = ""
    index = 0
    total = len(atoms)

    while index < total:
        parts: list[str] = [prefix] if prefix else []
        has_body = False

        while index < total:
            atom = atoms[index]
            candidate = [*parts, atom]
            candidate_tokens = count_tokens("\n\n".join(candidate))

            if has_body:
                if candidate_tokens > target_tokens:
                    break
            elif prefix and candidate_tokens > target_tokens + overlap_tokens:
                # F1c's hard ceiling, not just the soft `target_tokens`
                # budget, applies to this always-added first atom too. A
                # pre-bounded atom is `<= target_tokens` alone by
                # construction (see `_split_oversized_unit`), so dropping
                # the seeded `prefix` for this one chunk -- losing overlap
                # continuity at this single boundary rather than the bound
                # -- always brings it back under the ceiling.
                parts = []
                candidate = [atom]
                candidate_tokens = count_tokens(atom)

            parts = candidate
            has_body = True
            index += 1

        chunk_text = "\n\n".join(parts)
        chunks.append(chunk_text)
        prefix = _tail_tokens(chunk_text, overlap_tokens) if index < total else ""

    return chunks


def _split_oversized_unit(unit: str, target_tokens: int) -> list[str]:
    """Break one over-budget paragraph into pieces that each fit `target_tokens` alone.

    F1b's hard fallback, tried in two steps:

    1. Split on single newlines. A markdown table's rows or a tight list's
       items have no blank lines between them, so `_PARAGRAPH_SPLIT_RE`
       treats the whole block as one paragraph unit; splitting on `\\n`
       recovers row/item-level granularity, and most rows/items individually
       fit well within `target_tokens`.
    2. Any resulting line that is *still* over budget alone (a single
       unbroken run of text -- a giant table cell, a CJK paragraph with no
       ASCII whitespace, one long line with no newlines at all) is
       token-window-sliced via `_token_windows`, which always makes progress
       since a token window is capped by construction.

    The returned pieces are packed back up to `target_tokens` per chunk by
    `_split_long_section`'s packing loop (so an 80-row table doesn't become
    80 one-row chunks), which also applies the usual inter-chunk overlap.
    """
    if count_tokens(unit) <= target_tokens:
        return [unit]

    lines = [line for line in unit.split("\n") if line.strip()]
    if len(lines) <= 1:
        return _token_windows(unit, target_tokens)

    atoms: list[str] = []
    for line in lines:
        if count_tokens(line) <= target_tokens:
            atoms.append(line)
        else:
            atoms.extend(_token_windows(line, target_tokens))
    return atoms


def _token_windows(text: str, target_tokens: int) -> list[str]:
    """Slice `text` into consecutive, non-overlapping `target_tokens`-token windows.

    F1b's final fallback for a single line that alone still exceeds
    `target_tokens` even after newline-splitting. Always makes progress: each
    window advances by exactly `target_tokens` tokens, so this terminates in
    `ceil(count_tokens(text) / target_tokens)` windows regardless of `text`'s
    content. `overlap_tokens` between the resulting chunks is added exactly
    once, uniformly, when `_split_long_section`'s packing loop later packs
    these windows -- deliberately not duplicated here.
    """
    encoding = _encoding()
    ids = encoding.encode(text)
    return [
        _decode_clean(encoding, ids[i : i + target_tokens])
        for i in range(0, len(ids), target_tokens)
    ]


def _tail_tokens(text: str, n: int) -> str:
    """Return the exact trailing `n` tokens of `text`, decoded back to text.

    Round-tripping through `encode`/`decode` (rather than approximating with a
    word or character slice) guarantees the overlap is byte-for-byte identical
    to the corresponding suffix of `text`. `n <= 0` returns `""` explicitly
    (F2): `ids[-0:]` is `ids[:]` in Python, i.e. the *entire* token list, not
    zero tokens -- with the default packing loop's "seed the next chunk's
    prefix from the previous chunk's tail" step, an unguarded `n=0` silently
    reproduced the whole previous chunk as the next one's prefix, causing
    unbounded chunk growth when `overlap_tokens=0`.
    """
    if n <= 0:
        return ""
    encoding = _encoding()
    ids = encoding.encode(text)
    return _decode_clean(encoding, ids[-n:])


def _decode_clean(encoding: tiktoken.Encoding, ids: list[int]) -> str:
    """Decode a token-id slice to text without ever emitting U+FFFD (F4).

    `Encoding.decode` defaults to `errors="replace"`, which corrupts a slice
    whose bytes split a multi-byte UTF-8 character mid-sequence into U+FFFD
    replacement characters -- e.g. 9/10 chunks of an emoji-bearing document
    starting with U+FFFD, because `_tail_tokens`' suffix slice landed inside
    an emoji's byte sequence. Decoding via `decode_bytes` and stripping any
    leading UTF-8 continuation bytes (`0b10xxxxxx`, i.e. `b & 0xC0 == 0x80`)
    before `.decode("utf-8")` guarantees the returned text starts on a real
    character boundary. `errors="ignore"` on that final decode is a second,
    cheap safety net for slices whose *end* also splits a character -- only
    possible for `_token_windows`' interior windows (an arbitrary cut through
    the middle of a token stream), never for `_tail_tokens`' suffix slice,
    which always ends at the original, already-valid text's own end.
    """
    raw = encoding.decode_bytes(ids)
    start = 0
    while start < len(raw) and raw[start] & 0xC0 == 0x80:
        start += 1
    return raw[start:].decode("utf-8", errors="ignore")
