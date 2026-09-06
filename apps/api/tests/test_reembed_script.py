"""P7 remediation (fresh-review F1) — `scripts/reembed.py`, the first committed/tested bulk
re-embed tool.

Before this fix, there was NO committed, tested tooling to regenerate every published item's
chunks after an embedding-provider/model swap (the actual production re-embed after task 6R-14's
NVIDIA-EOL outage was a manual, uncommitted one-off run directly inside the live api container).
`app/services/content.py::publish_content` deliberately makes NO pipeline call when republishing
an already-published item (its own docstring: "'body unchanged since last embed' is the only
state reachable through the API/MCP surface" — true for a `body_md` edit, silently false for a
provider swap), so nothing in the existing API surface can force a bulk re-embed either.

This file seeds a small throwaway-schema corpus directly through the real content lifecycle
(`create_draft`/`publish_content`/`archive_content` — never a raw `Content`/`Chunk` row
construction, mirroring `app/seed.py`'s own "never a raw write" rule) with a `FakeEmbedder`-backed
`EmbeddingChunkPipeline` (the same fake-embedder-plus-real-pipeline pattern `tests/test_seed.py`/
`tests/test_lifecycle.py` already use — zero network, CONVENTIONS.md §10), then drives `scripts.
reembed.reembed_all` — the script's importable core-logic function — directly against a SECOND,
independent fake pipeline to prove every PUBLISHED, non-deleted item's chunks are genuinely
rebuilt through it (not just "some chunks exist," which the seeding step alone would already be
true of).

Imports `scripts/reembed.py` via the same sys.path-insertion technique every other
`scripts/mint_mcp_token.py`-importing test file already uses (it is not an installed package).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Chunk
from app.rag.pipeline import EmbeddingChunkPipeline
from app.services.content import archive_content, create_draft, publish_content

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

_DIMS = 1024


@dataclass
class FakeEmbedder:
    """Deterministic, recording fake `Embedder` (`app.rag.embeddings.Embedder` Protocol).

    Mirrors `tests/test_seed.py`/`tests/test_lifecycle.py`'s own `FakeEmbedder` — a fixed-width
    vector per text, no network call, ever."""

    dims: int = _DIMS
    calls: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    def embed_texts(
        self, texts: list[str], *, input_type: Literal["passage", "query"] = "passage"
    ) -> list[list[float]]:
        self.calls.append((tuple(texts), input_type))
        return [[0.1] * self.dims for _ in texts]


def _import_reembed_script() -> object:
    """Import `scripts/reembed.py` by inserting `scripts/` onto `sys.path` (it is not an
    installed package). Mirrors `tests/test_mcp_bearer_auth.py::_import_mint_script`."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    import reembed

    return reembed


def _chunk_count_for(session: Session, content_id: object) -> int:
    """Return the number of `Chunk` rows currently stored for `content_id`."""
    return int(
        session.execute(
            select(func.count()).select_from(Chunk).where(Chunk.content_id == content_id)
        ).scalar_one()
    )


def test_reembed_all_rebuilds_chunks_for_every_published_non_deleted_item(
    db_session: Session,
) -> None:
    """The core F1 pin: `reembed_all` visits every published, non-deleted item exactly once,
    rebuilding its chunks through the SUPPLIED pipeline (not merely leaving pre-existing ones
    alone), and returns an accurate `(item_count, chunk_count)` summary. A draft (never
    published) and an archived (published-then-archived, chunks already removed) item are both
    seeded alongside the two published ones and must be left untouched — `reembed_all` must
    neither visit them nor call the pipeline on their behalf."""
    reembed = _import_reembed_script()
    seed_pipeline = EmbeddingChunkPipeline(FakeEmbedder())

    published_one = create_draft(
        db_session,
        title="Roth IRA Conversion Basics",
        body_md="# Roth IRA\n\nSome real content about retirement accounts and conversions.",
        tags=[],
        actor_id=None,
    )
    publish_content(db_session, published_one.id, actor_id=None, pipeline=seed_pipeline)

    published_two = create_draft(
        db_session,
        title="Estate Planning 101",
        body_md="# Estate Planning\n\nSome real content about wills and trusts.",
        tags=[],
        actor_id=None,
    )
    publish_content(db_session, published_two.id, actor_id=None, pipeline=seed_pipeline)

    draft_only = create_draft(
        db_session,
        title="Draft Never Published",
        body_md="# Draft\n\nThis item is never published.",
        tags=[],
        actor_id=None,
    )

    archived = create_draft(
        db_session,
        title="Archived Item",
        body_md="# Archived\n\nThis item is published, then archived.",
        tags=[],
        actor_id=None,
    )
    publish_content(db_session, archived.id, actor_id=None, pipeline=seed_pipeline)
    archive_content(db_session, archived.id, actor_id=None, pipeline=seed_pipeline)
    db_session.flush()

    reembed_embedder = FakeEmbedder()
    reembed_pipeline = EmbeddingChunkPipeline(reembed_embedder)

    item_count, chunk_count = reembed.reembed_all(db_session, reembed_pipeline)
    db_session.flush()

    assert item_count == 2
    assert chunk_count > 0
    # Exactly two `embed_texts` calls — one per PUBLISHED item — through the NEW pipeline; the
    # draft and the archived item must never reach it.
    assert len(reembed_embedder.calls) == 2

    assert _chunk_count_for(db_session, published_one.id) > 0
    assert _chunk_count_for(db_session, published_two.id) > 0
    assert _chunk_count_for(db_session, draft_only.id) == 0
    assert _chunk_count_for(db_session, archived.id) == 0

    total_chunk_rows = int(db_session.execute(select(func.count()).select_from(Chunk)).scalar_one())
    assert total_chunk_rows == chunk_count


def test_reembed_all_returns_zero_zero_when_no_content_is_published(db_session: Session) -> None:
    """Empty-corpus edge case: no published items at all -> `(0, 0)`, no pipeline calls."""
    reembed = _import_reembed_script()
    fake_embedder = FakeEmbedder()
    pipeline = EmbeddingChunkPipeline(fake_embedder)

    item_count, chunk_count = reembed.reembed_all(db_session, pipeline)

    assert (item_count, chunk_count) == (0, 0)
    assert fake_embedder.calls == []
