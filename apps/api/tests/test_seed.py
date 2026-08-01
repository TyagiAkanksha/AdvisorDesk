"""Failing (RED) tests for the seed corpus, seed script, and eval question set (phase-4 task-04).

Task brief: docs/plans/phase-4-rag-assistant/task-04-seed-content-eval-set.md, Steps 2 + 6.
Spec: advisordesk-prd.md §8 (corpus: six tags, YAML frontmatter, ~20 files, 3-4 drafts, disclaimer
footer verbatim), §8.1 (`eval_questions.yaml` shape), §4.1 (seeded rows carry null actor columns).

Neither `app.seed` nor the corpus/eval files exist yet — the implementer (a separate agent per
CLAUDE.md's agent-separation rule) authors all three. Every DB-backed test below is expected to
fail at collection with `ModuleNotFoundError: No module named 'app.seed'` until `app/seed.py` is
created — that failure IS the RED evidence this file exists to produce. The pure-file corpus/eval
tests read `seed/sample_content/*.md` and `seed/eval_questions.yaml` directly and fail on
assertion (an empty directory / a missing file), never via `pytest.skip` — "SKIP-FREE" per the
dispatch brief.

pyyaml note (checked at authoring time): `apps/api`'s dependency group does not include `pyyaml`
yet (the implementer's Files-list dependency to add) — `uv run python -c "import yaml"` in this
project's own `.venv` raises `ModuleNotFoundError: No module named 'yaml'` today. `yaml` is
imported LOCALLY inside the two helpers that need it (`_parse_seed_file`, `_load_eval_questions`)
rather than at module top-level: `ruff`'s isort places any `import yaml` in the top-level block
BEFORE `from app.seed import ...` (straight imports sort ahead of from-imports within a section;
verified empirically against this file), which would make yaml's `ModuleNotFoundError` the one
Python actually raises during collection — masking the intended primary failure. Keeping `yaml`
out of the top-level block means collection fails solely on `from app.seed import SeedReport,
seed_all` (`ModuleNotFoundError: No module named 'app.seed'`), never reaching either local `import
yaml` line, so every test in this file shows the same, correct, primary RED reason.

Judgment call (test-author): PRD §8 says each file "has YAML frontmatter (title, tags, status)"
without pinning delimiter syntax. This file assumes the conventional `---`-fenced block at the top
of each markdown file (frontmatter YAML, then `---`, then the body) — the standard shape "YAML
frontmatter" denotes and the same block style PRD §8.1 uses for `eval_questions.yaml` itself. The
implementer's `app.seed` parser must agree with this exact shape for the corpus tests to pass at
GREEN; flagged in the test-author report for controller/reviewer sign-off.

Judgment call (test-author): the brief's Files list pins seed markdown files "named by slug, e.g.
`roth-ira-conversion-basics.md`" — every DB-backed assertion below therefore joins a seed file to
its resulting `Content` row by `Content.slug == <filename stem>` (never by title), which doubles as
a live pin of that naming convention: a title whose `_slugify` output doesn't match its filename
fails these tests loudly rather than silently matching on title text.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import make_session_factory
from app.models import Chunk, Content
from app.rag.pipeline import EmbeddingChunkPipeline
from app.seed import SeedReport, seed_all
from app.services.tags import tags_for_contents

# Repo root is four levels up from this file (tests/ -> api/ -> apps/ -> repo root) — computed
# rather than relying on pytest's cwd, since the brief's `content_dir=Path("seed/sample_content")`
# default is only meaningful relative to *some* working directory the implementer picks; these
# tests pass `content_dir` explicitly so they run correctly regardless (`cd apps/api && pytest ...`
# per this task's own pinned run command).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SEED_CONTENT_DIR = _REPO_ROOT / "seed" / "sample_content"
_EVAL_YAML_PATH = _REPO_ROOT / "seed" / "eval_questions.yaml"

# PRD §8's six corpus tags, verbatim.
_SIX_TAGS = {
    "retirement",
    "tax-planning",
    "estate-planning",
    "investing-basics",
    "college-savings",
    "insurance",
}

# PRD §8's disclaimer footer line, verbatim (copied via a script reading advisordesk-prd.md's raw
# UTF-8 bytes — the dash is U+2014 EM DASH, not a hyphen).
_FOOTER_LINE = "Sample content for demonstration purposes — not financial advice."

# nvidia/nv-embedqa-e5-v5's output width (PRD §7.2) / `chunks.embedding`'s pgvector column
# dimension (migration 0002) — mirrors `tests/test_lifecycle.py`'s own `EMBEDDING_DIMENSIONS`
# constant and its documented reason for being hardcoded rather than read off `Settings`.
_EMBEDDING_DIMENSIONS = 1024

_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\n(?P<frontmatter>.*?)\n---[ \t]*\n(?P<body>.*)\Z", re.DOTALL
)


# ---- fake embedder (brief: "no real provider calls") ----


@dataclass
class FakeEmbedder:
    """Deterministic, recording fake `Embedder` (`app.rag.embeddings.Embedder` Protocol).

    Mirrors `tests/test_lifecycle.py`'s `FakeEmbedder` — a fixed-width vector per text, no network
    call, ever. Nothing here asserts on vector *content*, so a simple constant vector (rather than
    `test_lifecycle.py`'s SHA-256-seeded one) is sufficient.
    """

    dims: int = _EMBEDDING_DIMENSIONS
    calls: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    def embed_texts(
        self, texts: list[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        self.calls.append((tuple(texts), input_type))
        return [[0.1] * self.dims for _ in texts]


@contextmanager
def _script_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit-then-close a session around one `seed_all` call or read.

    Mirrors how `app.seed`'s real `__main__` entry point (and every other top-level caller, per
    CONVENTIONS.md §3) owns the commit boundary — `seed_all`/the content services it calls through
    only `flush()`. No rollback branch: no test here exercises a failure path (out of scope for
    this task's Interfaces pin), unlike `test_lifecycle.py`'s `_route_session`.
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


# ---- corpus reading (pure file I/O, no DB) ----


def _parse_seed_file(path: Path) -> tuple[dict[str, Any], str]:
    """Split one seed markdown file into its parsed YAML frontmatter dict and raw body text."""
    import yaml  # local: see module docstring's pyyaml note

    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    assert match is not None, f"{path.name}: no ---delimited YAML frontmatter block found"
    frontmatter = yaml.safe_load(match.group("frontmatter"))
    assert isinstance(frontmatter, dict), f"{path.name}: frontmatter did not parse to a mapping"
    return frontmatter, match.group("body")


def _seed_md_files() -> list[Path]:
    """Every `*.md` file directly under `seed/sample_content/`, sorted by name.

    Asserts the directory itself exists first — an explicit failure, never a silent empty list
    masquerading as "zero files found" and never a `pytest.skip` (dispatch brief: corpus tests
    must be skip-free at RED).
    """
    assert _SEED_CONTENT_DIR.is_dir(), f"{_SEED_CONTENT_DIR} does not exist"
    return sorted(_SEED_CONTENT_DIR.glob("*.md"))


def _all_seed_records() -> list[dict[str, Any]]:
    """Every seed file, parsed: `{"path": Path, "frontmatter": dict, "body": str}`."""
    records = []
    for path in _seed_md_files():
        frontmatter, body = _parse_seed_file(path)
        records.append({"path": path, "frontmatter": frontmatter, "body": body})
    return records


# ---- corpus invariants (PRD §8 / brief Interfaces pin) ----


def test_seed_corpus_directory_exists_and_file_count_is_in_expected_band() -> None:
    """~20 files total (brief's pinned band: 19-21)."""
    files = _seed_md_files()
    assert 19 <= len(files) <= 21, (
        f"expected 19-21 seed files, found {len(files)}: {[f.name for f in files]}"
    )


def test_seed_corpus_every_file_has_title_tags_status_frontmatter() -> None:
    for record in _all_seed_records():
        frontmatter, path = record["frontmatter"], record["path"]
        assert isinstance(frontmatter.get("title"), str) and frontmatter["title"].strip(), (
            f"{path.name}: missing or blank 'title' in frontmatter"
        )
        assert isinstance(frontmatter.get("tags"), list) and frontmatter["tags"], (
            f"{path.name}: missing or empty 'tags' list in frontmatter"
        )
        assert "status" in frontmatter, f"{path.name}: missing 'status' in frontmatter"


def test_seed_corpus_status_is_published_or_draft() -> None:
    for record in _all_seed_records():
        status = record["frontmatter"].get("status")
        assert status in ("published", "draft"), f"{record['path'].name}: status={status!r}"


def test_seed_corpus_tags_are_subset_of_the_six_prd_tags() -> None:
    for record in _all_seed_records():
        tags = set(record["frontmatter"].get("tags") or [])
        unknown = tags - _SIX_TAGS
        assert not unknown, f"{record['path'].name}: tags {unknown} are not among the six §8 tags"


def test_seed_corpus_published_and_draft_counts_are_in_expected_bands() -> None:
    records = _all_seed_records()
    published = [r for r in records if r["frontmatter"].get("status") == "published"]
    drafts = [r for r in records if r["frontmatter"].get("status") == "draft"]
    assert 16 <= len(published) <= 17, f"expected 16-17 published, found {len(published)}"
    assert 3 <= len(drafts) <= 4, f"expected 3-4 drafts, found {len(drafts)}"
    assert len(published) + len(drafts) == len(records), (
        "every seed file must be either published or draft"
    )


def test_seed_corpus_each_of_the_six_tags_is_used_at_least_twice() -> None:
    counts: dict[str, int] = dict.fromkeys(_SIX_TAGS, 0)
    for record in _all_seed_records():
        for tag in record["frontmatter"].get("tags") or []:
            if tag in counts:
                counts[tag] += 1
    under_used = {tag: n for tag, n in counts.items() if n < 2}
    assert not under_used, f"tags used fewer than 2 times across the corpus: {under_used}"


def test_seed_corpus_every_body_ends_with_the_verbatim_disclaimer_footer_line() -> None:
    for record in _all_seed_records():
        lines = [line.strip() for line in record["body"].splitlines() if line.strip()]
        assert lines, f"{record['path'].name}: body has no content"
        assert lines[-1] == _FOOTER_LINE, (
            f"{record['path'].name}: last body line is {lines[-1]!r}, "
            f"expected the verbatim §8 footer {_FOOTER_LINE!r}"
        )


# ---- seed_all (real seed/sample_content/, fake pipeline) ----


def test_seed_all_creates_one_content_row_per_seed_file_with_correct_slug_tags_and_status(
    session_factory: sessionmaker[Session],
) -> None:
    records = _all_seed_records()
    pipeline = EmbeddingChunkPipeline(FakeEmbedder())

    with _script_session(session_factory) as session:
        report = seed_all(session, pipeline, content_dir=_SEED_CONTENT_DIR)

    assert isinstance(report, SeedReport)

    with _script_session(session_factory) as fresh:
        rows = list(fresh.execute(select(Content)).scalars())
        by_slug = {row.slug: row for row in rows}
        tag_names_by_content_id = tags_for_contents(fresh, [row.id for row in rows])

    assert len(rows) == len(records), (
        f"expected one Content row per seed file ({len(records)}), found {len(rows)}"
    )

    for record in records:
        slug = record["path"].stem
        assert slug in by_slug, (
            f"no Content row with slug={slug!r} for {record['path'].name} "
            f"(files are 'named by slug' per the brief); created slugs: {sorted(by_slug)}"
        )
        row = by_slug[slug]
        assert row.status == record["frontmatter"]["status"], (
            f"{slug}: status={row.status!r}, expected {record['frontmatter']['status']!r}"
        )
        assert set(tag_names_by_content_id[row.id]) == set(record["frontmatter"]["tags"]), (
            f"{slug}: persisted tags {tag_names_by_content_id[row.id]} != "
            f"frontmatter tags {record['frontmatter']['tags']}"
        )


def test_seed_all_drafts_have_zero_chunks_and_published_items_have_chunks(
    session_factory: sessionmaker[Session],
) -> None:
    records = _all_seed_records()
    pipeline = EmbeddingChunkPipeline(FakeEmbedder())

    with _script_session(session_factory) as session:
        seed_all(session, pipeline, content_dir=_SEED_CONTENT_DIR)

    with _script_session(session_factory) as fresh:
        rows = list(fresh.execute(select(Content)).scalars())
        by_slug = {row.slug: row for row in rows}
        chunk_counts = {
            row.id: fresh.execute(
                select(func.count()).select_from(Chunk).where(Chunk.content_id == row.id)
            ).scalar_one()
            for row in rows
        }

    for record in records:
        slug = record["path"].stem
        row = by_slug[slug]
        count = chunk_counts[row.id]
        if record["frontmatter"]["status"] == "draft":
            assert count == 0, f"{slug}: draft has {count} chunks, expected 0"
        else:
            assert count > 0, f"{slug}: published item has 0 chunks, expected >0"


def test_seed_all_actor_columns_are_null_on_every_seeded_row(
    session_factory: sessionmaker[Session],
) -> None:
    """PRD §4.1 pin: seed rows are written outside any admin session."""
    pipeline = EmbeddingChunkPipeline(FakeEmbedder())

    with _script_session(session_factory) as session:
        seed_all(session, pipeline, content_dir=_SEED_CONTENT_DIR)

    with _script_session(session_factory) as fresh:
        rows = list(fresh.execute(select(Content)).scalars())

    assert rows, "seed_all created no rows"
    for row in rows:
        assert row.author_id is None, f"{row.slug}: author_id is not null (§4.1 pin)"
        assert row.updated_by is None, f"{row.slug}: updated_by is not null (§4.1 pin)"


def test_seed_all_second_run_is_idempotent_all_skipped_row_count_unchanged(
    session_factory: sessionmaker[Session],
) -> None:
    records = _all_seed_records()
    pipeline = EmbeddingChunkPipeline(FakeEmbedder())

    with _script_session(session_factory) as session:
        first_report = seed_all(session, pipeline, content_dir=_SEED_CONTENT_DIR)

    with _script_session(session_factory) as fresh:
        row_count_after_first_run = fresh.execute(
            select(func.count()).select_from(Content)
        ).scalar_one()

    with _script_session(session_factory) as session:
        second_report = seed_all(session, pipeline, content_dir=_SEED_CONTENT_DIR)

    with _script_session(session_factory) as fresh:
        row_count_after_second_run = fresh.execute(
            select(func.count()).select_from(Content)
        ).scalar_one()

    assert first_report.created == len(records)
    assert row_count_after_second_run == row_count_after_first_run, (
        "a second seed_all run must not create additional Content rows"
    )
    assert second_report.created == 0
    assert second_report.skipped == len(records), (
        f"expected every one of {len(records)} files skipped on the second run, "
        f"got skipped={second_report.skipped}"
    )
    assert second_report.published == 0
    assert second_report.chunk_count == 0


def test_seed_all_first_run_report_numbers_match_the_real_corpus(
    session_factory: sessionmaker[Session],
) -> None:
    records = _all_seed_records()
    published_records = [r for r in records if r["frontmatter"]["status"] == "published"]
    pipeline = EmbeddingChunkPipeline(FakeEmbedder())

    with _script_session(session_factory) as session:
        report = seed_all(session, pipeline, content_dir=_SEED_CONTENT_DIR)

    assert report.created == len(records)
    assert report.skipped == 0
    assert report.published == len(published_records)

    with _script_session(session_factory) as fresh:
        total_chunk_rows = fresh.execute(select(func.count()).select_from(Chunk)).scalar_one()

    assert report.chunk_count == total_chunk_rows
    assert report.chunk_count > 0


# ---- eval_questions.yaml (PRD §8.1) ----


def _load_eval_questions() -> list[dict[str, Any]]:
    import yaml  # local: see module docstring's pyyaml note

    assert _EVAL_YAML_PATH.is_file(), f"{_EVAL_YAML_PATH} does not exist"
    data = yaml.safe_load(_EVAL_YAML_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list), "eval_questions.yaml must parse to a top-level list"
    return data


def test_eval_questions_yaml_parses_as_a_list_of_dicts_with_exactly_the_three_keys() -> None:
    items = _load_eval_questions()
    assert items, "eval_questions.yaml is empty"
    expected_keys = {"question", "expected_slugs", "answerable"}
    for item in items:
        assert isinstance(item, dict), f"item is not a mapping: {item!r}"
        assert set(item.keys()) == expected_keys, (
            f"item has keys {set(item.keys())}, expected exactly {expected_keys}"
        )
        assert isinstance(item["question"], str) and item["question"].strip(), (
            f"item has a blank/non-string question: {item!r}"
        )
        assert isinstance(item["expected_slugs"], list), (
            f"item's expected_slugs is not a list: {item!r}"
        )
        assert isinstance(item["answerable"], bool), f"item's answerable is not a bool: {item!r}"


def test_eval_questions_answerable_entries_expected_slugs_all_exist_in_published_seed_corpus() -> (
    None
):
    items = _load_eval_questions()
    published_slugs = {
        record["path"].stem
        for record in _all_seed_records()
        if record["frontmatter"]["status"] == "published"
    }
    answerable = [item for item in items if item["answerable"] is True]
    assert len(answerable) >= 12, f"expected >=12 answerable questions, found {len(answerable)}"
    for item in answerable:
        assert item["expected_slugs"], f"answerable question has empty expected_slugs: {item!r}"
        unknown = set(item["expected_slugs"]) - published_slugs
        assert not unknown, (
            f"question {item['question']!r} references slugs not in the published corpus: {unknown}"
        )


def test_eval_questions_unanswerable_entries_have_empty_expected_slugs() -> None:
    items = _load_eval_questions()
    unanswerable = [item for item in items if item["answerable"] is False]
    assert len(unanswerable) >= 3, f"expected >=3 unanswerable questions, found {len(unanswerable)}"
    for item in unanswerable:
        assert item["expected_slugs"] == [], (
            f"question {item['question']!r} is unanswerable but expected_slugs="
            f"{item['expected_slugs']!r}, expected []"
        )
