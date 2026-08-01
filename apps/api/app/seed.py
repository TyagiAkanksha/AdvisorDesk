"""Seed the sample advisory corpus through the real content lifecycle (PRD §8, §4.1).

`seed_all` loads every `seed/sample_content/*.md` file (frontmatter: `title`, `tags`, `status`)
and, for each one whose slug does not already exist, creates a draft through
`app.services.content.create_draft` and — for files marked `status: published` — publishes it
through `app.services.content.publish_content`, which runs the real
`ChunkPipeline.rebuild_chunks` (chunk + embed + insert, PRD §4's atomic publish transaction). This
module never constructs a `Content`/`Chunk` row itself and never issues a raw write — every mutation
goes through those two service functions, exactly as `docs/plans/phase-4-rag-assistant/
task-04-seed-content-eval-set.md`'s Context section requires ("the seed script goes THROUGH these
services... never raw SQL/ORM writes").

Idempotency (PRD §8: seeding is safe to re-run) is checked with one read — `select(Content.id)
.where(Content.title == title)` — deliberately not routed through any existing
`app.services.content` read helper: `get_content`/`list_content` filter to active (non-soft-deleted)
rows via `active_select`, and `get_published_by_slug` additionally requires `status == 'published'`;
none of them can answer "does ANY row, active or not, published or draft, already own this title" —
the exact question idempotency needs. This mirrors `app.services.content.generate_slug`'s own
documented exception to the active-read convention, for the identical reason: existence must be
checked directly, not through a filtered service. The read never appears inside the same module as
a write elsewhere in this codebase (`app.services` is the only ORM-touching layer per
CONVENTIONS.md §2) — but `app.seed`, like `app.main`, is a top-level wiring/script module outside
that layer diagram, not a `routes`/`mcp` caller `services` exists to keep from duplicating business
logic between. Every WRITE still goes through `create_draft`/`publish_content`.

**Keyed on TITLE, not slug or filename (review round 1, finding I1).** `create_draft` always
derives the persisted slug from `title` via `app.services.content.generate_slug`, which is
collision-aware: if a row with the "natural" (unsuffixed) slug for a title already exists,
`generate_slug` returns a DIFFERENT, `-2`/`-3`-suffixed slug instead — its contract is "give me an
AVAILABLE slug," which by definition returns something NEW whenever the natural base is taken.
Calling `generate_slug` a second time here, purely to compute a check key, is therefore NOT a fix:
on a re-run, it would report the (as yet unoccupied) suffixed slug as "not found" and re-create the
row anyway — reproducing the exact bug this check exists to close, one level removed. Checking by
TITLE sidesteps this: `title` is the one identity that must agree between a seed file and its
previously-created row regardless of what slug `generate_slug` (correctly) assigned it, whether or
not the file's own name happens to match that slug. PRD §8 requires no filename-slug agreement; the
21 committed `seed/sample_content/*.md` files satisfy it anyway (verified live by
`tests/test_seed.py`'s DB-backed slug-join test), but a user-supplied `content_dir` is not bound by
that pinned test — `tests/test_seed_guards.py` exercises exactly this mismatch case directly.

Seeded rows are created with `actor_id=None` (PRD §4.1: "seeded rows carry `author_id = null` /
`updated_by = null` (created outside any session)") — `create_draft`/`publish_content` already
support this via their `actor_id: uuid.UUID | None` parameter; this module simply always passes
`None`.

Runnable directly: `python -m app.seed` (the `__main__` block below) wires the real `Settings`,
a real `Engine`/session factory (`app.db`, mirroring `app/main.py`'s own wiring), and a real
`EmbeddingChunkPipeline` backed by `OpenAICompatibleEmbedder` — the only place in this module a real
provider is ever touched. Tests (`tests/test_seed.py`) call `seed_all` directly against a fake
`EmbeddingChunkPipeline(FakeEmbedder())`, so no test in this codebase ever makes a real embedding
call through this module.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_engine, make_session_factory
from app.models import Chunk, Content
from app.rag.embeddings import OpenAICompatibleEmbedder
from app.rag.pipeline import EmbeddingChunkPipeline
from app.services.content import create_draft, publish_content
from app.services.lifecycle import ChunkPipeline

logger = logging.getLogger(__name__)

# PRD §8: "seed/sample_content/ contains ~20 markdown files" — the default `content_dir` `seed_all`
# is called with when a caller does not override it (brief Interfaces pin: `seed_all(session,
# pipeline, content_dir=Path("seed/sample_content"))`). Relative to whatever process cwd `seed_all`
# is called from — every test in `tests/test_seed.py` passes `content_dir` explicitly instead (a
# test's cwd is not guaranteed to be the repo root), and `_run_from_cli` below does too, computed
# off `_REPO_ROOT` rather than this bare relative default, since the task's own pinned Real Run
# command (`cd apps/api && ... && uv run python -m app.seed`) runs with `apps/api` as the process
# cwd, not the repo root this literal string would resolve against.
_DEFAULT_CONTENT_DIR: Path = Path("seed/sample_content")

# `app/seed.py` -> `app/` -> `apps/api/` -> `apps/` -> repo root: four `.parent`s up, mirroring
# `tests/test_seed.py`'s own `_REPO_ROOT` computation (same file depth: both live at
# `apps/api/<dir>/<file>.py`).
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]

# Matches the test-author's own `_FRONTMATTER_RE` (tests/test_seed.py) byte-for-byte: a leading
# `---` line, the YAML frontmatter block, a closing `---` line, then the Markdown body — the
# "conventional `---`-fenced" shape that file's module docstring flags as the one judgment call the
# implementer's parser must agree with for the corpus/eval tests to pass at GREEN.
_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\n(?P<frontmatter>.*?)\n---[ \t]*\n(?P<body>.*)\Z", re.DOTALL
)


@dataclass(frozen=True)
class SeedReport:
    """Summary counts from one `seed_all` run (brief Interfaces pin; PRD §9.1 metric inputs).

    Args:
        created: number of new `Content` rows added this run (one per seed file whose slug did
            not already exist).
        published: of those newly created rows, how many were published (`status: published` in
            frontmatter) through the real embed pipeline.
        skipped: number of seed files whose slug already existed — an idempotent no-op, nothing
            about that row is touched.
        chunk_count: total number of `Chunk` rows written this run, summed across every published
            item (`0` on a re-run where everything is skipped).
    """

    created: int
    published: int
    skipped: int
    chunk_count: int


def _parse_seed_file(path: Path) -> tuple[dict[str, Any], str]:
    """Split one seed markdown file into its parsed YAML frontmatter dict and raw Markdown body.

    Args:
        path: the seed `.md` file to read.

    Returns:
        `(frontmatter, body)` — `frontmatter` is the parsed YAML mapping (`title`, `tags`,
        `status`, per PRD §8); `body` is everything after the closing `---` fence, unmodified.

    Raises:
        ValueError: `path`'s contents do not match the `---`-fenced frontmatter shape, or the
            frontmatter block does not parse to a YAML mapping.
    """
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise ValueError(f"{path}: no ---delimited YAML frontmatter block found")
    frontmatter = yaml.safe_load(match.group("frontmatter"))
    if not isinstance(frontmatter, dict):
        raise ValueError(f"{path}: frontmatter did not parse to a mapping")
    return frontmatter, match.group("body")


def _already_seeded(session: Session, title: str) -> bool:
    """Return whether any `Content` row — any status, active or soft-deleted — already has `title`.

    The idempotency check PRD §8 requires: a re-run of `seed_all` must skip a file whose title was
    already created by a prior run, without touching that row. See the module docstring's
    "Keyed on TITLE, not slug or filename" section for why this checks `title`, not `slug` or the
    seed file's filename stem — the short version: `generate_slug` is collision-aware, so re-calling
    it here to compute a check key would itself return a different (as yet unoccupied) suffixed
    slug on a re-run, silently defeating the check. This is also a direct read rather than a call
    through an existing `app.services.content` helper — every one of those filters by
    active/published status, which would wrongly report a soft-deleted or draft row as "not seeded"
    and attempt to create a duplicate.

    **`.limit(1)` is required (review round 2, finding I2): `Content.title` carries no unique
    constraint** — unlike `Content.slug` (`unique=True`, `app/models/content.py`), which the
    round-1 slug-keyed check was implicitly safe against by construction. PRD §4's `-2`/`-3`
    slug-suffix rule exists precisely because duplicate titles are legal: the admin UI
    (`POST /content`) and, from phase 5, the agent's `create_draft` MCP tool can both create two
    `Content` rows sharing one title. Without `.limit(1)`, `scalar_one_or_none()` raises
    `sqlalchemy.exc.MultipleResultsFound` the moment two such rows exist and a seed file happens to
    share their title — aborting the whole run instead of skipping. `.limit(1)` makes this function
    answer "does at least one row exist," not "does exactly one," which is the only question
    idempotency actually needs.

    Args:
        session: the caller's `Session`.
        title: the candidate title (a seed file's frontmatter `title`).

    Returns:
        `True` if at least one `Content` row with this exact title already exists.
    """
    return (
        session.execute(
            select(Content.id).where(Content.title == title).limit(1)
        ).scalar_one_or_none()
        is not None
    )


def _chunk_count_for(session: Session, content_id: Any) -> int:
    """Return the number of `Chunk` rows currently stored for `content_id`.

    Used only for `SeedReport.chunk_count` bookkeeping right after `publish_content` has run —
    `publish_content` itself returns the published `Content` row, not a chunk count, and its
    signature is not part of this task's Files list to change. A read-only count query is cheaper
    and simpler than re-deriving the count from `pipeline.rebuild_chunks`'s return value, which
    `publish_content` already consumed internally.
    """
    return int(
        session.execute(
            select(func.count()).select_from(Chunk).where(Chunk.content_id == content_id)
        ).scalar_one()
    )


def seed_all(
    session: Session,
    pipeline: ChunkPipeline,
    *,
    content_dir: Path = _DEFAULT_CONTENT_DIR,
) -> SeedReport:
    """Load every `content_dir/*.md` seed file, creating (and publishing) it through the real
    services.

    For each file, sorted by filename for deterministic ordering: if a `Content` row already has
    that file's frontmatter `title` (see the module docstring's "Keyed on TITLE" section for why),
    the file is skipped (idempotency, PRD §8). Otherwise, a draft is created via `create_draft`
    (title/tags/body from the file's frontmatter/body, `actor_id=None` per PRD §4.1) and, if the
    frontmatter's `status` is `"published"`, immediately published via `publish_content` — which
    runs the real chunk + embed + insert transaction through `pipeline` (PRD §4's atomic publish
    rule). Files marked `status: "draft"` are left as drafts (PRD §8: "3-4 as drafts so the agent
    has content to find/publish in demos").

    Args:
        session: the caller's `Session`. Per CONVENTIONS.md §3, this function only `flush()`es (via
            the service functions it calls) — it never `commit()`s or `rollback()`s; the caller owns
            the transaction boundary (the `__main__` block below, for a real run).
        pipeline: the `ChunkPipeline` `publish_content` chunks and embeds through — a fake in tests
            (`tests/test_seed.py`'s `FakeEmbedder`-backed `EmbeddingChunkPipeline`), the real
            `EmbeddingChunkPipeline(OpenAICompatibleEmbedder(...))` when run via `__main__`.
        content_dir: the directory of `*.md` seed files to load. Defaults to
            `seed/sample_content` relative to the process's current working directory.

    Returns:
        A `SeedReport` summarizing what this run did.
    """
    created = 0
    published = 0
    skipped = 0
    chunk_count = 0

    for path in sorted(content_dir.glob("*.md")):
        frontmatter, body = _parse_seed_file(path)
        title = str(frontmatter["title"])
        tags = [str(tag) for tag in frontmatter.get("tags") or []]
        status = str(frontmatter["status"])

        if _already_seeded(session, title):
            skipped += 1
            logger.info("seed: %s (title=%r) already exists — skipped", path.name, title)
            continue

        content = create_draft(session, title=title, body_md=body, tags=tags, actor_id=None)
        created += 1

        if status == "published":
            publish_content(session, content.id, actor_id=None, pipeline=pipeline)
            item_chunk_count = _chunk_count_for(session, content.id)
            chunk_count += item_chunk_count
            published += 1
            logger.info("seed: published %s (%d chunks)", content.slug, item_chunk_count)
        else:
            logger.info("seed: created draft %s", content.slug)

    return SeedReport(
        created=created, published=published, skipped=skipped, chunk_count=chunk_count
    )


def _run_from_cli() -> None:
    """Entry point for `python -m app.seed`: wires real settings/engine/pipeline, then seeds.

    Mirrors `app/main.py`'s own wiring (`Settings()` -> `make_engine` -> `make_session_factory`,
    `OpenAICompatibleEmbedder.from_settings` -> `EmbeddingChunkPipeline`) but scoped to only what
    seeding needs — no FastAPI app, no OAuth client, no chat LLM, no rate limiter. Commits once on
    success (the whole run is one transaction, matching how `app.routes.deps.get_session` commits a
    real request) and rolls back on any error, so a failure partway through never leaves a partially
    seeded, partially committed run — `seed_all` itself only `flush()`es.

    Raises:
        SystemExit: `DATABASE_URL` is empty — `make_engine("")` would otherwise fail with an opaque
            driver error instead of a clear message naming the missing env var.
    """
    settings = Settings()
    database_url = settings.database_url.get_secret_value()
    if not database_url:
        raise SystemExit(
            "DATABASE_URL is required to run `python -m app.seed`. Set it (PRD §9) and export it "
            "into the environment — e.g. `set -a && source .env && set +a` — before running this "
            "script."
        )

    engine = make_engine(database_url)
    session_factory = make_session_factory(engine)
    embedder = OpenAICompatibleEmbedder.from_settings(settings)
    pipeline = EmbeddingChunkPipeline(embedder)

    session = session_factory()
    try:
        report = seed_all(session, pipeline, content_dir=_REPO_ROOT / "seed" / "sample_content")
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(
        f"seed_all: created={report.created} published={report.published} "
        f"skipped={report.skipped} chunk_count={report.chunk_count}"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _run_from_cli()
