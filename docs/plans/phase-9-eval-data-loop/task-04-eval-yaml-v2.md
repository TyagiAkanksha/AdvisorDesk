---
id: p9-t04
phase: phase-9-eval-data-loop
depends_on: [p9-t03]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: sonnet
---

# Task 04 — `eval_questions.yaml` v2: classes, personas, `expected_chunks`, reference answers

## Goal

The golden set stops being one-dimensional. The loader accepts four new **optional** keys —
`class` (→ `question_class`), `persona`, `expected_chunks` (`slug#heading-slug`),
`reference_answer` — with defaults that keep today's 21-question file valid byte-for-byte, and
`test_seed.py`'s pins move from "exactly three keys" to `REQUIRED ⊆ keys ⊆ REQUIRED ∪ OPTIONAL`
plus class-membership and `expected_chunks`-consistency checks. A new resolver turns
`slug#heading-slug` into real `chunks.id` values by matching the heading line every chunk starts
with (`app/rag/chunking.py`: a heading is always a chunk boundary), so task 05's recall@k survives
re-chunking. `EvalResult.question_class`/`persona` (columns from task 01) start being persisted.

No new question content is authored here — that is tasks 10-14. This task is the *schema* and the
*machinery*.

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §B2 (the v2 key list, the six classes, the
  `off_domain ⇒ not answerable` rule, the `test_seed.py` pin rewrite).
- `apps/api/app/eval/groundedness.py:97-103` (`_EvalQuestion`), `:203-238` (`_load_questions`),
  `:241-294` (`_evaluate_question`), `:318-362` (`run_eval`) — all at the post-task-03 state.
- `apps/api/app/rag/chunking.py:141-161` (`_split_sections`: every ATX heading starts a section,
  and the section text BEGINS with its heading line) and `:30-32` (`_HEADING_RE`).
- `apps/api/app/services/content.py:25-31` — `_SLUG_INVALID_RE` / `_slugify`, the exact
  lowercase-hyphenate rule `slugify_heading` must mirror.
- `apps/api/app/services/queries.py` — `active_select`.
- `apps/api/tests/test_seed.py:382-438` — the three eval pins this task rewrites, and
  `_all_seed_records()`/`_EVAL_YAML_PATH` above them.
- `seed/eval_questions.yaml` — the current 21-question file (21 items, 17 answerable).
- `apps/api/app/models/chunks.py:41-47` — `Chunk.id/content_id/chunk_index/text`.

## Files

**Create**
- `apps/api/app/eval/questions.py`
- `apps/api/tests/test_eval_questions_v2.py`

**Modify**
- `apps/api/app/eval/groundedness.py` (import the loader from the new module; delete
  `_EvalQuestion`/`_load_questions`; carry `question_class`/`persona` onto `EvalRow`)
- `apps/api/tests/test_seed.py` (the three eval pins)

**Not modified:** `seed/eval_questions.yaml` (it must keep validating unchanged — that is the
back-compat proof).

## Interfaces

### `app/eval/questions.py`

```python
QUESTION_CLASSES: frozenset[str] = frozenset(
    {"answerable", "multi_source", "near_miss", "off_domain", "threshold", "stale_number"}
)
REQUIRED_KEYS: frozenset[str] = frozenset({"question", "expected_slugs", "answerable"})
OPTIONAL_KEYS: frozenset[str] = frozenset(
    {"class", "persona", "expected_chunks", "reference_answer"}
)


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


def load_questions(questions_path: Path) -> list[EvalQuestion]:
    """Load and validate a v2 eval-question file.

    Raises:
        ValueError: not a top-level list; an item is not a mapping; a required key is missing or
            mistyped; an unknown key is present; `class` is not in `QUESTION_CLASSES`; a
            `class: off_domain` item has `answerable: true`; an `expected_chunks` entry is not
            `"<slug>#<heading-slug>"`; an `expected_chunks` slug is not in that item's
            `expected_slugs`.
    """


def resolve_expected_chunks(session: Session, refs: Sequence[str]) -> set[uuid.UUID]:
    """Resolve `"<slug>#<heading-slug>"` references to live `chunks.id` values.

    For each ref: find the published, non-deleted `Content` with that slug (`active_select`); of
    its chunks, return the one whose FIRST line is an ATX heading whose slugified text equals
    `heading-slug`. A ref that resolves to nothing is skipped silently — the golden set is
    authored against seed markdown, and a chunk can legitimately be absent on a corpus the run is
    measuring (that is exactly the `retrieval_miss` vs `corpus_gap` distinction task 06 draws, and
    raising here would abort a whole eval run over one stale reference).
    """
```

Defaults applied by `load_questions`:

| Key | Default |
|---|---|
| `class` | `"answerable"` when `answerable` is true, else `"off_domain"` |
| `persona` | `None` |
| `expected_chunks` | `[]` |
| `reference_answer` | `None` |

Ref grammar: `^[a-z0-9][a-z0-9-]*#[a-z0-9][a-z0-9-]*$`.

Heading match: a chunk's first line, stripped, must match `^#{1,6} (?P<text>.+)$`; compare
`slugify_heading(text) == heading_slug`. Ambiguity rule: if several chunks of one content match,
take the lowest `chunk_index` (document order) and add all of them to the returned set is wrong —
**return the single lowest-`chunk_index` match**, so precision@k stays meaningful.

### `app/eval/groundedness.py`

- Delete `_EvalQuestion` and `_load_questions`; `from app.eval.questions import EvalQuestion,
  load_questions`. `run_eval` calls `load_questions(Path(questions_path))`.
- `_evaluate_question` sets `question_class=question.question_class` and
  `persona=question.persona` on the returned `EvalRow` (fields added in task 03).
- Re-export `EvalQuestion`/`load_questions` from `groundedness.__all__`? **No** — importers use
  `app.eval.questions` directly. Leave `__all__` as-is plus nothing new.

### `apps/api/tests/test_seed.py` rewrite (the three pins at lines 394-438)

Replace `test_eval_questions_yaml_parses_as_a_list_of_dicts_with_exactly_the_three_keys` with the
subset pin + class membership + `expected_chunks` consistency; keep both other tests' bodies
(the ">=12 answerable", "slugs are published stems", ">=3 unanswerable, empty expected_slugs"
assertions) exactly as they are.

## Steps (TDD)

- [ ] **RED — test-author, 1/2.** Create `apps/api/tests/test_eval_questions_v2.py`:

```python
"""v2 eval-question loader + `expected_chunks` resolution (phase-9 task-04, DESIGN §B2)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from sqlalchemy.orm import Session

from app.eval.questions import (
    OPTIONAL_KEYS,
    QUESTION_CLASSES,
    REQUIRED_KEYS,
    load_questions,
    resolve_expected_chunks,
    slugify_heading,
)
from app.models import Chunk, Content


def _write(tmp_path: Path, items: list[dict[str, object]]) -> Path:
    path = tmp_path / "eval_questions.yaml"
    path.write_text(yaml.safe_dump(items, sort_keys=False), encoding="utf-8")
    return path


def test_v1_records_still_load_with_v2_defaults(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            {"question": "What is an RSU?", "expected_slugs": ["rsus-at-vest"], "answerable": True},
            {"question": "Crypto staking?", "expected_slugs": [], "answerable": False},
        ],
    )

    questions = load_questions(path)

    assert [q.question_class for q in questions] == ["answerable", "off_domain"]
    assert questions[0].persona is None
    assert questions[0].expected_chunks == []
    assert questions[0].reference_answer is None


def test_every_optional_key_is_parsed(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            {
                "question": "What happens to my RSUs when they vest?",
                "expected_slugs": ["rsus-at-vest"],
                "answerable": True,
                "class": "multi_source",
                "persona": "Sam",
                "expected_chunks": ["rsus-at-vest#what-happens-at-vest"],
                "reference_answer": "They are taxed as ordinary income at vest.",
            }
        ],
    )

    question = load_questions(path)[0]

    assert question.question_class == "multi_source"
    assert question.persona == "Sam"
    assert question.expected_chunks == ["rsus-at-vest#what-happens-at-vest"]
    assert question.reference_answer.startswith("They are taxed")


def test_the_committed_seed_file_still_validates() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    questions = load_questions(repo_root / "seed" / "eval_questions.yaml")

    assert len(questions) >= 21
    assert all(q.question_class in QUESTION_CLASSES for q in questions)


@pytest.mark.parametrize(
    "item, fragment",
    [
        ({"question": "q", "expected_slugs": [], "answerable": True, "class": "bogus"}, "class"),
        (
            {"question": "q", "expected_slugs": [], "answerable": True, "class": "off_domain"},
            "off_domain",
        ),
        ({"question": "q", "expected_slugs": [], "answerable": True, "extra": 1}, "unknown"),
        (
            {
                "question": "q",
                "expected_slugs": ["a"],
                "answerable": True,
                "expected_chunks": ["no-hash-here"],
            },
            "expected_chunks",
        ),
        (
            {
                "question": "q",
                "expected_slugs": ["a"],
                "answerable": True,
                "expected_chunks": ["b#heading"],
            },
            "expected_slugs",
        ),
    ],
)
def test_invalid_records_raise_value_error(
    tmp_path: Path, item: dict[str, object], fragment: str
) -> None:
    path = _write(tmp_path, [item])

    with pytest.raises(ValueError) as excinfo:
        load_questions(path)

    assert fragment in str(excinfo.value)


def test_required_and_optional_key_sets_are_disjoint_and_named_per_design() -> None:
    assert REQUIRED_KEYS == {"question", "expected_slugs", "answerable"}
    assert OPTIONAL_KEYS == {"class", "persona", "expected_chunks", "reference_answer"}
    assert not REQUIRED_KEYS & OPTIONAL_KEYS


def test_slugify_heading_matches_the_content_slug_rule() -> None:
    assert slugify_heading("What happens at vest?") == "what-happens-at-vest"
    assert slugify_heading("Key numbers (2026)") == "key-numbers-2026"
    assert slugify_heading("  ISOs vs NSOs  ") == "isos-vs-nsos"


def test_resolve_expected_chunks_matches_the_chunk_that_starts_with_the_heading(
    db_session: Session,
) -> None:
    content = Content(
        title="RSUs at vest",
        slug="rsus-at-vest",
        body_md="unused",
        status="published",
        published_at=datetime.now(UTC),
    )
    db_session.add(content)
    db_session.flush()
    intro = Chunk(content_id=content.id, chunk_index=0, text="Intro paragraph, no heading.")
    target = Chunk(
        content_id=content.id,
        chunk_index=1,
        text="## What happens at vest?\n\nYour shares are delivered and taxed.",
    )
    other = Chunk(
        content_id=content.id,
        chunk_index=2,
        text="## Key numbers (2026)\n\nThe supplemental rate is 22%.",
    )
    db_session.add_all([intro, target, other])
    db_session.flush()

    resolved = resolve_expected_chunks(
        db_session, ["rsus-at-vest#what-happens-at-vest", "rsus-at-vest#key-numbers-2026"]
    )

    assert resolved == {target.id, other.id}


def test_resolve_expected_chunks_skips_unknown_slug_heading_and_unpublished_content(
    db_session: Session,
) -> None:
    draft = Content(title="Draft", slug="draft-article", body_md="x", status="draft")
    db_session.add(draft)
    db_session.flush()
    db_session.add(Chunk(content_id=draft.id, chunk_index=0, text="## Hidden\n\nbody"))
    db_session.flush()

    assert resolve_expected_chunks(db_session, ["draft-article#hidden"]) == set()
    assert resolve_expected_chunks(db_session, ["nope#nothing"]) == set()
```

- [ ] **RED — test-author, 2/2.** In `apps/api/tests/test_seed.py`, replace
  `test_eval_questions_yaml_parses_as_a_list_of_dicts_with_exactly_the_three_keys` (lines 394-409)
  with exactly:

```python
_REQUIRED_EVAL_KEYS = {"question", "expected_slugs", "answerable"}
_OPTIONAL_EVAL_KEYS = {"class", "persona", "expected_chunks", "reference_answer"}
_EVAL_CLASSES = {
    "answerable",
    "multi_source",
    "near_miss",
    "off_domain",
    "threshold",
    "stale_number",
}


def test_eval_questions_yaml_items_carry_the_required_keys_and_only_known_optional_ones() -> None:
    """Phase-9 DESIGN §B2: v2 widens the shape from "exactly three keys" to
    REQUIRED ⊆ keys ⊆ REQUIRED ∪ OPTIONAL, with class membership and an
    `off_domain ⇒ not answerable` rule."""
    items = _load_eval_questions()
    assert items, "eval_questions.yaml is empty"
    for item in items:
        assert isinstance(item, dict), f"item is not a mapping: {item!r}"
        keys = set(item.keys())
        assert _REQUIRED_EVAL_KEYS <= keys, f"item is missing required keys: {item!r}"
        unknown = keys - _REQUIRED_EVAL_KEYS - _OPTIONAL_EVAL_KEYS
        assert not unknown, f"item has unknown keys {unknown}: {item!r}"
        assert isinstance(item["question"], str) and item["question"].strip(), (
            f"item has a blank/non-string question: {item!r}"
        )
        assert isinstance(item["expected_slugs"], list), (
            f"item's expected_slugs is not a list: {item!r}"
        )
        assert isinstance(item["answerable"], bool), f"item's answerable is not a bool: {item!r}"
        question_class = item.get("class", "answerable" if item["answerable"] else "off_domain")
        assert question_class in _EVAL_CLASSES, (
            f"item's class {question_class!r} is not one of {_EVAL_CLASSES}: {item!r}"
        )
        if question_class == "off_domain":
            assert item["answerable"] is False, (
                f"off_domain question marked answerable: {item!r}"
            )
        for ref in item.get("expected_chunks", []):
            assert isinstance(ref, str) and "#" in ref, (
                f"expected_chunks entry is not '<slug>#<heading-slug>': {ref!r}"
            )
            assert ref.split("#", 1)[0] in item["expected_slugs"], (
                f"expected_chunks entry {ref!r} names a slug outside expected_slugs: {item!r}"
            )
        if "persona" in item:
            assert isinstance(item["persona"], str) and item["persona"].strip()
        if "reference_answer" in item:
            assert isinstance(item["reference_answer"], str) and item["reference_answer"].strip()
```

  Leave `test_eval_questions_answerable_entries_expected_slugs_all_exist_in_published_seed_corpus`
  and `test_eval_questions_unanswerable_entries_have_empty_expected_slugs` untouched.

- [ ] **Run RED:** `cd apps/api && TEST_DATABASE_URL=… uv run pytest tests/test_eval_questions_v2.py
  tests/test_seed.py -q` → the new module's tests fail on `ModuleNotFoundError:
  app.eval.questions`; the rewritten `test_seed` pin fails only if the implementer's defaults
  disagree (it should PASS against today's file — note that in the RED evidence and explain that
  this particular pin is a *widening*, so its RED is the new-module import error only).

- [ ] **GREEN — implementer.** Create `app/eval/questions.py` per Interfaces, rewire
  `groundedness.py`, and carry `question_class`/`persona` into `EvalRow` so `record_run`
  (task 03) persists them.

- [ ] **Run GREEN:** the two files above, then `uv run pytest -q`.

- [ ] **Gates:** `pnpm gates:api` (incl. `lint-imports` — `app.eval` may import `app.models`/
  `app.services`, so the resolver is legal where it sits).

- [ ] **Commit:** `git commit -m "feat(api): eval_questions.yaml v2 loader + expected_chunks resolution (p9 t04)"`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=… uv run pytest tests/test_eval_questions_v2.py tests/test_seed.py \
  tests/test_groundedness.py -q
pnpm gates:api
git diff --exit-code -- ../../seed/eval_questions.yaml   # must PASS: v2 is back-compatible
```

## Acceptance

- The committed 21-question file loads unchanged and yields `question_class` defaults
  (`answerable` / `off_domain`).
- Every listed invalid shape raises `ValueError` naming the offending key.
- `resolve_expected_chunks` matches a chunk by its leading heading line, ignores drafts and
  soft-deleted content, returns the lowest-`chunk_index` match on ties, and skips unresolvable
  refs without raising.
- `EvalResult.question_class`/`persona` are populated by a persisted run.
- `seed/eval_questions.yaml` is byte-identical to `main` after this task.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-04-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-04-implementer.md`
