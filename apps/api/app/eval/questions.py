"""`seed/eval_questions.yaml` v2 loader + `expected_chunks` resolution (phase-9 DESIGN §B2, task
04). Extracted from `app.eval.groundedness` (which owned the v1, three-key loader) so the eval
question SCHEMA — classes, personas, `expected_chunks` references, reference answers — has its
own home, independent of the harness that drives questions through retrieval + synthesis.

`load_questions` widens the v1 shape (`question`, `expected_slugs`, `answerable` — exactly those
three keys) to REQUIRED ⊆ keys ⊆ REQUIRED ∪ OPTIONAL, with per-key defaults chosen so today's
21-question file loads byte-for-byte unchanged (`test_the_committed_seed_file_still_validates`,
`tests/test_seed.py`'s widened pin). `resolve_expected_chunks` turns an authored
`"<slug>#<heading-slug>"` reference into a live `chunks.id` by matching the heading line every
chunk produced by `app.rag.chunking._split_sections` starts with — so a golden question's
expected-chunk pin survives re-chunking (task 05's recall@k) instead of hard-coding a chunk id
that would need re-authoring on every corpus change.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Content
from app.services.queries import active_select

QUESTION_CLASSES: frozenset[str] = frozenset(
    {"answerable", "multi_source", "near_miss", "off_domain", "threshold", "stale_number"}
)
REQUIRED_KEYS: frozenset[str] = frozenset({"question", "expected_slugs", "answerable"})
OPTIONAL_KEYS: frozenset[str] = frozenset(
    {"class", "persona", "expected_chunks", "reference_answer"}
)

# Ref grammar (task brief Interfaces): `<slug>#<heading-slug>`, both halves lowercase-hyphenated
# tokens that don't start or end with a hyphen.
_REF_RE = re.compile(r"^[a-z0-9][a-z0-9-]*#[a-z0-9][a-z0-9-]*$")

# A chunk's first line, stripped, is an ATX heading iff it matches this (task brief: "a chunk's
# first line, stripped, must match `^#{1,6} (?P<text>.+)$`").
_HEADING_LINE_RE = re.compile(r"^#{1,6} (?P<text>.+)$")

# Mirrors `app.services.content._SLUG_INVALID_RE` exactly — see `slugify_heading`'s docstring for
# why this is a deliberate duplication, not an import.
_SLUG_INVALID_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class EvalQuestion:
    """One parsed, validated `seed/eval_questions.yaml` v2 record (DESIGN §B2)."""

    question: str
    expected_slugs: list[str]
    answerable: bool
    question_class: str
    persona: str | None
    expected_chunks: list[str]
    reference_answer: str | None


def slugify_heading(heading_text: str) -> str:
    """Lowercase-hyphenate one heading's text, exactly as `app.services.content._slugify` does.

    Duplicated deliberately rather than imported: `_slugify` is private to the content service and
    slugifies TITLES for the `content.slug` column; this slugifies HEADING text for an eval-file
    reference. Same rule, two different contracts — a future change to one must not silently move
    the other. (Pinned by `test_slugify_heading_matches_the_content_slug_rule`.)
    """
    return _SLUG_INVALID_RE.sub("-", heading_text.strip().lower()).strip("-")


def load_questions(questions_path: Path) -> list[EvalQuestion]:
    """Load and validate a v2 eval-question file.

    Raises:
        ValueError: not a top-level list; an item is not a mapping; a required key is missing or
            mistyped; an unknown key is present; `class` is not in `QUESTION_CLASSES`; a
            `class: off_domain` item has `answerable: true`; an `expected_chunks` entry is not
            `"<slug>#<heading-slug>"`; an `expected_chunks` slug is not in that item's
            `expected_slugs`; two items share the same `question` text (carried over from the v1
            loader, `app.eval.groundedness`'s former `_load_questions` — the `(run_id, question)`
            unique constraint on `EvalResult` would otherwise reject a whole run at `record_run`'s
            final `flush()`, after the run already paid for its embedder/chat/judge calls; pinned
            by `tests/test_groundedness.py::
            test_run_eval_rejects_duplicate_question_text_before_any_retrieval_or_answering`);
            an `answerable: false` item carries a `reference_answer` (phase-9 N5 ruling);
    """
    raw = yaml.safe_load(Path(questions_path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{questions_path}: eval questions file must parse to a top-level list")

    questions: list[EvalQuestion] = []
    seen_questions: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{questions_path}[{index}]: item is not a mapping: {item!r}")

        keys = set(item.keys())
        missing = REQUIRED_KEYS - keys
        if missing:
            raise ValueError(
                f"{questions_path}[{index}]: item is missing required key(s) {missing}: {item!r}"
            )
        unknown = keys - REQUIRED_KEYS - OPTIONAL_KEYS
        if unknown:
            raise ValueError(
                f"{questions_path}[{index}]: item has unknown key(s) {unknown}: {item!r}"
            )

        question = item.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"{questions_path}[{index}]: 'question' must be a non-blank string")
        if question in seen_questions:
            raise ValueError(f"{questions_path}[{index}]: duplicate question: {question!r}")
        seen_questions.add(question)

        expected_slugs = item.get("expected_slugs")
        if not isinstance(expected_slugs, list):
            raise ValueError(f"{questions_path}[{index}]: 'expected_slugs' must be a list")
        expected_slugs = [str(slug) for slug in expected_slugs]

        answerable = item.get("answerable")
        if not isinstance(answerable, bool):
            raise ValueError(f"{questions_path}[{index}]: 'answerable' must be a bool")

        question_class = item.get("class", "answerable" if answerable else "off_domain")
        if question_class not in QUESTION_CLASSES:
            raise ValueError(
                f"{questions_path}[{index}]: 'class' {question_class!r} is not one of "
                f"{sorted(QUESTION_CLASSES)}: {item!r}"
            )
        if question_class == "off_domain" and answerable:
            raise ValueError(
                f"{questions_path}[{index}]: class 'off_domain' item has answerable=True: {item!r}"
            )

        expected_chunks_raw = item.get("expected_chunks", [])
        if not isinstance(expected_chunks_raw, list):
            raise ValueError(f"{questions_path}[{index}]: 'expected_chunks' must be a list")
        expected_chunks: list[str] = []
        for ref in expected_chunks_raw:
            if not isinstance(ref, str) or not _REF_RE.match(ref):
                raise ValueError(
                    f"{questions_path}[{index}]: expected_chunks entry {ref!r} is not "
                    "'<slug>#<heading-slug>'"
                )
            ref_slug = ref.split("#", 1)[0]
            if ref_slug not in expected_slugs:
                raise ValueError(
                    f"{questions_path}[{index}]: expected_chunks entry {ref!r} names a slug "
                    f"outside expected_slugs: {item!r}"
                )
            expected_chunks.append(ref)

        persona = item.get("persona")
        if persona is not None and (not isinstance(persona, str) or not persona.strip()):
            raise ValueError(
                f"{questions_path}[{index}]: 'persona' must be a non-blank string: {item!r}"
            )

        reference_answer = item.get("reference_answer")
        if reference_answer is not None and (
            not isinstance(reference_answer, str) or not reference_answer.strip()
        ):
            raise ValueError(
                f"{questions_path}[{index}]: 'reference_answer' must be a non-blank string: "
                f"{item!r}"
            )

        if reference_answer is not None and not answerable:
            raise ValueError(
                f"{questions_path}[{index}]: 'reference_answer' is not allowed on an "
                f"answerable=False item (phase-9 N5 ruling: a reference answer on a row the corpus "
                f"must NOT answer gives the answer-relevance and context-recall judges a target "
                f"that cannot be supported, scoring a correct refusal as a miss): {item!r}"
            )

        questions.append(
            EvalQuestion(
                question=question,
                expected_slugs=expected_slugs,
                answerable=answerable,
                question_class=question_class,
                persona=persona,
                expected_chunks=expected_chunks,
                reference_answer=reference_answer,
            )
        )
    return questions


def resolve_expected_chunks(session: Session, refs: Sequence[str]) -> set[uuid.UUID]:
    """Resolve `"<slug>#<heading-slug>"` references to live `chunks.id` values.

    For each ref: find the published, non-deleted `Content` with that slug (`active_select`); of
    its chunks, return the one whose FIRST line is an ATX heading whose slugified text equals
    `heading-slug`. A ref that resolves to nothing is skipped silently — the golden set is
    authored against seed markdown, and a chunk can legitimately be absent on a corpus the run is
    measuring (that is exactly the `retrieval_miss` vs `corpus_gap` distinction task 06 draws, and
    raising here would abort a whole eval run over one stale reference).
    """
    resolved: set[uuid.UUID] = set()
    for ref in refs:
        slug, _, heading_slug = ref.partition("#")
        content = session.scalars(
            active_select(Content).where(Content.slug == slug, Content.status == "published")
        ).first()
        if content is None:
            continue

        chunks = session.scalars(
            select(Chunk).where(Chunk.content_id == content.id).order_by(Chunk.chunk_index)
        ).all()
        for chunk in chunks:
            first_line = chunk.text.splitlines()[0].strip() if chunk.text else ""
            match = _HEADING_LINE_RE.match(first_line)
            if match and slugify_heading(match.group("text")) == heading_slug:
                resolved.add(chunk.id)
                break
    return resolved
