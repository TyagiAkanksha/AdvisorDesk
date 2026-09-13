"""v2 eval-question loader + `expected_chunks` resolution (phase-9 task-04, DESIGN §B2).

ruff isort note (checked at authoring time, mirrors `test_seed.py`'s own pyyaml import-order
note): with `app/eval/questions.py` not yet created (this task's RED state), `ruff check` cannot
resolve it as a first-party module and sorts the `from app.eval.questions import (...)` block as
if it were third-party, ahead of `from sqlalchemy.orm import Session` — flagging this file's
otherwise-correct import order (`sqlalchemy` before the two `app.*` blocks) as `I001`. Verified
empirically: stubbing `app/eval/questions.py` in a scratch copy makes `ruff check` accept this
EXACT ordering with zero diff, and instead flags the ruff-suggested "fix" (which reorders around
the still-missing module) once the module is real. The import order below is therefore the
GREEN-state-correct one, left as authored rather than "fixed" to satisfy a transient RED-only
isort quirk that self-resolves the moment the implementer creates `app/eval/questions.py`.
"""

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


def test_reference_answer_on_an_unanswerable_row_raises(tmp_path: Path) -> None:
    """Phase-9 N5 ruling, now enforced by the loader: a reference answer on a row the corpus must
    not answer hands the answer-relevance and context-recall judges an unsupportable target, which
    scores a correct refusal as a miss."""
    path = _write(
        tmp_path,
        [
            {
                "question": "How is my token compensation taxed?",
                "expected_slugs": [],
                "answerable": False,
                "class": "near_miss",
                "reference_answer": "It is ordinary income when you gain control of it.",
            }
        ],
    )

    with pytest.raises(ValueError) as excinfo:
        load_questions(path)

    message = str(excinfo.value)
    assert "reference_answer" in message
    assert "answerable" in message


def test_unanswerable_rows_without_a_reference_answer_still_load(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            {
                "question": "How is my token compensation taxed?",
                "expected_slugs": [],
                "answerable": False,
                "class": "near_miss",
                "persona": "Marcus",
            }
        ],
    )

    question = load_questions(path)[0]

    assert question.question_class == "near_miss"
    assert question.reference_answer is None
    assert question.expected_chunks == []
