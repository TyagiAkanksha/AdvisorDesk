"""Bulk re-embed every published content item (PRD §4, §7.2; P7 remediation F1).

The provider swap task 6R-14 (both pinned NVIDIA models going EOL, 410 Gone) needed every
published item's chunks regenerated under the newly-active embedding provider/model — the
production re-embed at the time was a manual, uncommitted, untested one-off invocation of
`EmbeddingChunkPipeline.rebuild_chunks` run directly inside the live api container (`.superpowers/
sdd/progress.md:356,363`). This script is the committed, tested replacement: it re-chunks +
re-embeds EVERY published, non-deleted `Content` row via the SAME non-destructive per-item
primitive `publish`/edit already use (`app.rag.pipeline.EmbeddingChunkPipeline.rebuild_chunks`) —
content rows themselves are never touched, only their `Chunk` rows are deleted and reinserted, one
item's transaction at a time within the caller's session boundary.

Mirrors `app/seed.py`'s `_run_from_cli` wiring (`Settings()` -> `make_engine` ->
`make_session_factory`, `OpenAICompatibleEmbedder.from_settings` -> `EmbeddingChunkPipeline`) —
unlike `scripts/mint_mcp_token.py` (which deliberately reads only `DATABASE_URL` straight from
`os.environ` to avoid demanding every other env var a one-shot token CLI never needs), this script
genuinely needs the full LLM provider configuration (`LLM_PROVIDER`, the active provider's API
key, `LLM_BASE_URL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`) to build a real embedder, so it
reads `DATABASE_URL` + those settings together through one `Settings()` instance — the same single
config surface (CONVENTIONS.md §7) every other provider-touching module already uses.

`reembed_all` is the importable core logic — a plain `(session, pipeline) -> (item_count,
chunk_count)` function with no CLI/env/provider dependency of its own — so `tests/test_reembed_
script.py` can drive it directly against a throwaway-schema DB and a fake, no-network pipeline
(mirroring `app/seed.py::seed_all`'s identical test-vs-`main()` split). `main()` is the only thing
that reads `DATABASE_URL`, builds a real engine/session, or constructs a real
`OpenAICompatibleEmbedder` — no test in this codebase ever makes a real embedding call through
this module.

Usage:
    uv run python scripts/reembed.py
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import Settings
from app.db import make_engine, make_session_factory
from app.rag.embeddings import OpenAICompatibleEmbedder
from app.rag.pipeline import EmbeddingChunkPipeline
from app.services.content import list_published_content
from app.services.lifecycle import ChunkPipeline


def reembed_all(session: Session, pipeline: ChunkPipeline) -> tuple[int, int]:
    """Rebuild chunks for every published, non-deleted `Content` row, via `pipeline`.

    Reads the current item list with `app.services.content.list_published_content` (the same
    active-row + `status == 'published'` filter the public `/public/content` feed uses, PRD §5.3)
    and calls `pipeline.rebuild_chunks(session, content)` once per item — the identical
    non-destructive primitive `publish_content`/`update_content` already call on a real request,
    so an item's OLD chunks are deleted and its NEW ones inserted atomically per item, never both
    halves of the corpus in an inconsistent in-between state (a failure partway through leaves
    every item processed so far re-embedded and every item after it untouched — still a fully
    consistent state for each individual item, since `rebuild_chunks` itself is only ever
    `flush()`-only; see its own docstring for the atomicity this composes with).

    Args:
        session: the caller's `Session`. Per CONVENTIONS.md §3, this function only `flush()`s (via
            `pipeline.rebuild_chunks`) — it never `commit()`s or `rollback()`s; the caller (`main`
            below, for a real run) owns the transaction boundary.
        pipeline: the `ChunkPipeline` to rebuild through — the real
            `EmbeddingChunkPipeline(OpenAICompatibleEmbedder.from_settings(...))` when run via
            `main()`, a fake (`FakeEmbedder`-backed) one in tests.

    Returns:
        `(item_count, chunk_count)` — `item_count` is how many published items were processed;
        `chunk_count` is the total number of chunk rows written across all of them.
    """
    items = list_published_content(session)
    total_chunks = 0
    for content in items:
        chunk_count = pipeline.rebuild_chunks(session, content)
        total_chunks += chunk_count
        print(f"reembed: {content.slug} ({chunk_count} chunks)")
    return len(items), total_chunks


def main() -> None:
    """Wire real settings/engine/pipeline, re-embed every published item, commit once, print a
    summary.

    Mirrors `app/seed.py::_run_from_cli`'s wiring exactly, scoped to only what re-embedding
    needs — no FastAPI app, no OAuth client, no chat LLM, no rate limiter. Commits once on
    success (the whole run is one transaction) and rolls back on any error, so a failure partway
    through never leaves a partially committed run.

    Raises:
        SystemExit: `DATABASE_URL` is empty — `make_engine("")` would otherwise fail with an
            opaque driver error instead of a clear message naming the missing env var.
    """
    settings = Settings()
    database_url = settings.database_url.get_secret_value()
    if not database_url:
        raise SystemExit(
            "DATABASE_URL is required to run `python scripts/reembed.py`. Set it (PRD §9) and "
            "export it into the environment — e.g. `set -a && source .env && set +a` — before "
            "running this script."
        )

    engine = make_engine(database_url)
    session_factory = make_session_factory(engine)
    embedder = OpenAICompatibleEmbedder.from_settings(settings)
    pipeline = EmbeddingChunkPipeline(embedder)

    session = session_factory()
    try:
        item_count, chunk_count = reembed_all(session, pipeline)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"reembed_all: items={item_count} chunks={chunk_count}")


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    main()
