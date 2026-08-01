"""Regression tests for phase-4 task-04 review rounds 1-2 (`app/seed.py`).

Task brief: docs/plans/phase-4-rag-assistant/task-04-seed-content-eval-set.md.

Round 1, finding I1: `seed_all`'s idempotency check previously keyed on a seed file's filename
stem, while `create_draft` (via `app.services.content.generate_slug`) actually persists a slug
derived from the file's frontmatter `title`. When the two disagree — impossible for the 21
committed `seed/sample_content/*.md` files (`tests/test_seed.py`'s own DB-backed slug-join test
pins title-slugifies-to-filename for all of them), but not guaranteed for an out-of-repo/
user-supplied `content_dir` — every re-run of `seed_all` would silently re-create the row with a
`-2`, `-3`, ... collision-suffixed slug and re-embed it, forever (review probe B, reproduced
independently below). Fixed by keying `_already_seeded` on `title` instead.

Round 2, finding I2: `Content.title` carries no unique constraint (unlike `Content.slug`), so two
pre-existing rows sharing a title made `_already_seeded`'s `scalar_one_or_none()` raise
`sqlalchemy.exc.MultipleResultsFound`, aborting the whole run instead of skipping. PRD §4's
`-2`/`-3` slug-suffix rule exists precisely because duplicate titles are legal (the admin UI, and
from phase 5 the agent's `create_draft` MCP tool, can both create them). Fixed by adding
`.limit(1)` before `scalar_one_or_none()`.

Uses the same `FakeEmbedder`/`EmbeddingChunkPipeline`/`_script_session` shapes
`tests/test_seed.py` already established, duplicated here rather than imported — no test file in
this suite imports fixtures/fakes from another (CONVENTIONS.md §10: unique test-file basenames, no
shared `conftest.py` fixture for either), mirroring the existing `test_seed.py`/`test_lifecycle.py`
precedent of each defining its own `session_factory` fixture off `tmp_engine`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import make_session_factory
from app.models import Chunk, Content
from app.rag.pipeline import EmbeddingChunkPipeline
from app.seed import seed_all
from app.services.content import create_draft

# nvidia/nv-embedqa-e5-v5's output width (PRD §7.2) — mirrors tests/test_seed.py's own constant.
_EMBEDDING_DIMENSIONS = 1024

# Filename stem deliberately does NOT slugify-match the frontmatter title below
# ("a-totally-different-title") — the exact mismatch shape review probe B reproduced.
_MISMATCHED_FILENAME = "my-article.md"

_MISMATCHED_FILE_BODY = """---
title: A Totally Different Title
tags:
  - retirement
status: published
---

# A Totally Different Title

This is throwaway regression-test content for the seed script's title-keyed idempotency guard. It
exists only to give `chunk_markdown` something to chunk; it is not part of the real seed corpus and
is not subject to that corpus's footer/word-count/tag conventions.
"""


@dataclass
class FakeEmbedder:
    """Deterministic, no-network-call fake `Embedder` — mirrors `tests/test_seed.py`'s own."""

    dims: int = _EMBEDDING_DIMENSIONS
    calls: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    def embed_texts(
        self, texts: list[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        self.calls.append((tuple(texts), input_type))
        return [[0.1] * self.dims for _ in texts]


@contextmanager
def _script_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit-then-close a session around one `seed_all` call or read — mirrors
    `tests/test_seed.py`'s own `_script_session`, matching how `app.seed`'s real `__main__` entry
    point owns the commit boundary (CONVENTIONS.md §3: services only `flush()`).
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture
def session_factory(tmp_engine: Engine) -> sessionmaker[Session]:
    """A session factory bound to the throwaway-schema `tmp_engine` (CONVENTIONS.md §10)."""
    return make_session_factory(tmp_engine)


def test_seed_all_second_run_skips_a_file_whose_stem_disagrees_with_its_slugified_title(
    tmp_path: Path, session_factory: sessionmaker[Session]
) -> None:
    """I1 regression: filename stem != generate_slug(title) must not defeat idempotency.

    Run 1 creates exactly one row, whose persisted slug is the title's natural (unsuffixed) slug —
    NOT the mismatched filename stem. Run 2 must skip it entirely: no second row, no `-2`-suffixed
    sibling slug anywhere, and no new chunks (proving the file was not silently re-embedded).
    """
    content_dir = tmp_path / "mismatched_content"
    content_dir.mkdir()
    (content_dir / _MISMATCHED_FILENAME).write_text(_MISMATCHED_FILE_BODY, encoding="utf-8")

    pipeline = EmbeddingChunkPipeline(FakeEmbedder())

    with _script_session(session_factory) as session:
        first_report = seed_all(session, pipeline, content_dir=content_dir)

    with _script_session(session_factory) as fresh:
        rows_after_first = list(fresh.execute(select(Content)).scalars())
        chunks_after_first = fresh.execute(select(func.count()).select_from(Chunk)).scalar_one()

    assert first_report.created == 1
    assert first_report.skipped == 0
    assert first_report.published == 1
    assert first_report.chunk_count > 0
    assert len(rows_after_first) == 1
    # The persisted slug is derived from the TITLE, not the mismatched filename stem
    # ("my-article") — this is what `generate_slug("A Totally Different Title")` actually
    # produces when nothing else claims that slug yet.
    assert rows_after_first[0].slug == "a-totally-different-title"

    with _script_session(session_factory) as session:
        second_report = seed_all(session, pipeline, content_dir=content_dir)

    with _script_session(session_factory) as fresh:
        rows_after_second = list(fresh.execute(select(Content)).scalars())
        chunks_after_second = fresh.execute(select(func.count()).select_from(Chunk)).scalar_one()

    assert second_report.created == 0
    assert second_report.skipped == 1
    assert second_report.published == 0
    assert second_report.chunk_count == 0

    # No duplicate row: still exactly one, and it's the SAME row (not a new one with a new id).
    assert len(rows_after_second) == 1
    assert rows_after_second[0].id == rows_after_first[0].id
    assert rows_after_second[0].slug == "a-totally-different-title"

    # No suffixed sibling was ever created, on either run — the bug this test guards against.
    all_slugs = {row.slug for row in rows_after_second}
    assert "a-totally-different-title-2" not in all_slugs
    assert "my-article" not in all_slugs

    # No re-embedding happened on the skipped second run.
    assert chunks_after_second == chunks_after_first


def test_seed_all_does_not_raise_when_two_pre_existing_rows_share_a_title(
    tmp_path: Path, session_factory: sessionmaker[Session]
) -> None:
    """I2 regression: `_already_seeded` must tolerate a non-unique `title`.

    `Content.title` carries no unique constraint (`Content.slug` does) — PRD §4's `-2`/`-3`
    slug-suffix rule exists precisely because two rows can legitimately share a title, created
    through the admin UI or (phase 5) the agent's `create_draft` MCP tool. Seeds two such rows
    directly through the real `create_draft` service (never through `seed_all`, which would itself
    skip the second one), then runs `seed_all` over a one-file directory whose frontmatter carries
    that exact title. Before the `.limit(1)` fix, `_already_seeded`'s `scalar_one_or_none()` raised
    `sqlalchemy.exc.MultipleResultsFound` the instant it saw two matching rows, aborting the whole
    run; after the fix, `seed_all` must complete without raising and report the file as skipped.
    """
    duplicate_title = "Admin Collision Title"

    with _script_session(session_factory) as session:
        create_draft(
            session,
            title=duplicate_title,
            body_md="First admin-created draft sharing this title.",
            tags=[],
            actor_id=None,
        )
        create_draft(
            session,
            title=duplicate_title,
            body_md="Second admin-created draft sharing this title.",
            tags=[],
            actor_id=None,
        )

    with _script_session(session_factory) as fresh:
        rows_before = list(
            fresh.execute(select(Content).where(Content.title == duplicate_title)).scalars()
        )

    # Sanity: the DB really does have a duplicate-title pair, with distinct slugs (the -2 suffix
    # rule) — exactly the precondition `_already_seeded` must survive.
    assert len(rows_before) == 2
    assert len({row.slug for row in rows_before}) == 2

    content_dir = tmp_path / "duplicate_title_content"
    content_dir.mkdir()
    (content_dir / "collision.md").write_text(
        f"""---
title: {duplicate_title}
tags:
  - retirement
status: draft
---

# {duplicate_title}

Throwaway body for the I2 duplicate-title regression test — not part of the real seed corpus.
""",
        encoding="utf-8",
    )

    pipeline = EmbeddingChunkPipeline(FakeEmbedder())

    with _script_session(session_factory) as session:
        report = seed_all(session, pipeline, content_dir=content_dir)  # must not raise

    assert report.created == 0
    assert report.skipped == 1
    assert report.published == 0
    assert report.chunk_count == 0

    with _script_session(session_factory) as fresh:
        rows_after = list(
            fresh.execute(select(Content).where(Content.title == duplicate_title)).scalars()
        )

    # Still exactly the two pre-existing rows — seed_all added nothing.
    assert len(rows_after) == 2
    assert {row.id for row in rows_after} == {row.id for row in rows_before}
