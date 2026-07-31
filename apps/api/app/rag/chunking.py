"""Deterministic markdown chunking for the RAG pipeline (PRD §7.1, v1.5).

Pure, dependency-light, and leaf-clean: no I/O, no imports from any other `app.*`
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
    split on markdown headings (`^#{1,6} `) into sections; a section that fits
    within `target_tokens` is packed whole into a single chunk (never merged
    with a neighboring section -- every heading is always a chunk boundary); a
    section longer than `target_tokens` is split on paragraph boundaries
    (blank lines), packing whole paragraphs up to `target_tokens` per chunk,
    with the trailing `overlap_tokens` tokens of each chunk repeated as the
    leading tokens of the next chunk from the same section. `chunk_index` is
    0-based document order. An empty or whitespace-only body returns `[]`.

    Args:
        body_md: the content item's markdown body.
        target_tokens: soft per-chunk token budget (PRD §7.1 default: 400).
        overlap_tokens: trailing/leading token overlap between adjacent
            chunks produced by splitting one long section (default: 50).

    Returns:
        `ChunkData` instances in document order, `chunk_index` 0-based and
        contiguous. `[]` for an empty/whitespace-only `body_md`.
    """
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
    progress is guaranteed even if a single unit alone exceeds the budget.
    Each subsequent chunk (beyond the section's first) is seeded with the
    exact trailing `overlap_tokens` tokens of the previous chunk's text,
    decoded straight from the tokenizer so the overlap is a verbatim
    substring -- not a reconstruction that could drift from the original
    wording.
    """
    units = [unit for unit in _PARAGRAPH_SPLIT_RE.split(section) if unit.strip()]
    if not units:
        return []

    chunks: list[str] = []
    prefix = ""
    index = 0
    total = len(units)

    while index < total:
        parts = [prefix] if prefix else []
        current_tokens = count_tokens(prefix) if prefix else 0
        has_body = False

        while index < total:
            unit = units[index]
            unit_tokens = count_tokens(unit)
            if has_body and current_tokens + unit_tokens > target_tokens:
                break
            parts.append(unit)
            current_tokens += unit_tokens
            has_body = True
            index += 1

        chunk_text = "\n\n".join(parts)
        chunks.append(chunk_text)
        prefix = _tail_tokens(chunk_text, overlap_tokens) if index < total else ""

    return chunks


def _tail_tokens(text: str, n: int) -> str:
    """Return the exact trailing `n` tokens of `text`, decoded back to text.

    Round-tripping through `encode`/`decode` (rather than approximating with a
    word or character slice) guarantees the overlap is byte-for-byte identical
    to the corresponding suffix of `text`.
    """
    encoding = _encoding()
    ids = encoding.encode(text)
    return encoding.decode(ids[-n:])
