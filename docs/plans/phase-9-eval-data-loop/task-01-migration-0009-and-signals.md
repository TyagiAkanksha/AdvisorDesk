---
id: p9-t01
phase: phase-9-eval-data-loop
depends_on: []
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: opus
---

# Task 01 — Migration 0009: eval tables, feedback/latency signals, per-citation similarity

## Goal

One additive migration (`0009_eval_and_feedback`) lands the whole phase-9 schema: the three new
tables (`eval_runs`, `eval_results`, `content_proposals`) and two new `chat_messages` columns
(`feedback`, `latency_ms`). Two serve-time signals start being written: every persisted assistant
row's `citations` JSONB entry gains the `similarity` the retriever already computed and drops
today (`app/services/chat.py:135-143`), and `latency_ms` is written from the `time.monotonic()`
the chat route already takes (`app/routes/public_routes.py:391`). No route signature, DTO, or MCP
tool changes — `openapi.json`/`mcp-tools.json` must NOT move in this task.

`content_proposals` is created here and left inert until task 16 (INDEX plan-time ruling);
`eval_runs.kind` and `eval_results.metrics` are created here so tasks 05/06/07 need no second
migration (INDEX plan-time ruling + DESIGN "one migration").

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §"Part A", §B1, §D (`content_proposals`),
  §"Migration `0009_eval_and_feedback`".
- `docs/plans/phase-9-eval-data-loop/00-INDEX.md` §"Global Constraints" (schema-parity, gates).
- `apps/api/app/models/base.py` — `_NAMING_CONVENTION` (lines 22-28), `uuid_pk()`,
  `TimestampMixin`, `UpdatedAtMixin`.
- `apps/api/app/models/content.py:24-26` — the `CheckConstraint("status in (...)", name="…")`
  idiom (enums are text + CHECK, never PG ENUM).
- `apps/api/app/models/oauth.py:136-137` — the multi-column `UniqueConstraint(..., name="uq_…")`
  idiom (explicit literal name, not a convention token).
- `apps/api/app/models/chat.py` — the whole file (25 lines of model).
- `apps/api/app/models/__init__.py` — the import + `__all__` registry every new model joins.
- `apps/api/alembic/versions/0001_initial_schema.py:96-126` (JSONB/REAL/`op.f()` idiom) and
  `apps/api/alembic/versions/0007_oauth_tables.py` (multi-table create/drop order, `op.f()`
  constraint names) and `0008_drop_oauth_consents_revoked_at.py` (revision header shape).
- `apps/api/tests/test_models_schema.py:154-176` — the parity gate this task must keep green.
- `apps/api/tests/conftest.py` — `tmp_engine`/`db_session`, and how Alembic is driven
  (`_ALEMBIC_INI`, `_ALEMBIC_SCRIPT_LOCATION`, `MIGRATE_SCHEMA`) — copied by the round-trip test.
- `apps/api/app/services/chat.py:30-61` (`RetrievedChunkLike`/`RetrievalResultLike`) and
  `:107-154` (`record_assistant_message`).
- `apps/api/app/rag/retrieval.py:38-53` — `RetrievedChunk.similarity` (already a float on every
  chunk `retrieve()` returns).
- `apps/api/app/routes/public_routes.py:160-281` (`_generate_chat_stream`) and `:372-415`
  (`public_chat`, `_start = time.monotonic()` at line 391).
- `apps/api/tests/test_public_chat.py:191-201` (`_chunk_level_citation`), `:271-292`
  (`_build_client`), `:420-466` (the citation-asymmetry test this task edits).

## Files

**Create**
- `apps/api/app/models/eval.py`
- `apps/api/alembic/versions/0009_eval_and_feedback.py`
- `apps/api/tests/test_eval_models.py`
- `apps/api/tests/test_migration_0009_roundtrip.py`

**Modify**
- `apps/api/app/models/chat.py` (two columns + one CHECK)
- `apps/api/app/models/__init__.py` (register `EvalRun`, `EvalResult`, `ContentProposal`)
- `apps/api/app/services/chat.py` (`similarity` on the protocol + in the citation dict;
  `latency_ms` parameter)
- `apps/api/app/routes/public_routes.py` (thread the monotonic start into the generator)
- `apps/api/tests/test_public_chat.py` (citation shape + one new latency assertion)

**Must NOT change:** `apps/api/openapi.json`, `apps/api/mcp-tools.json`, either app's
`schema.d.ts`.

## Interfaces

### `eval_runs` (model `EvalRun`, `TimestampMixin`)

| Column | Type | Null | Default |
|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` |
| `created_at` | timestamptz | no | `now()` |
| `kind` | text | no | `'answer'`; CHECK `kind in ('answer', 'agent')` |
| `label` | text | no | — |
| `git_sha` | text | no | `''` |
| `embedding_model` | text | no | — |
| `chat_model` | text | no | — |
| `judge_model` | text | no | — |
| `similarity_threshold` | float (double precision) | no | — |
| `retrieval_k` | integer | no | — |
| `corpus_content_count` | integer | no | — |
| `corpus_chunk_count` | integer | no | — |
| `corpus_max_updated_at` | timestamptz | yes | — |
| `corpus_digest` | text | no | — |
| `total_questions` | integer | no | — |
| `pct_fully_supported` | float | no | — |
| `refusal_correct` | integer | no | — |
| `refusal_total` | integer | no | — |

Index `ix_eval_runs_kind_created` on `(kind, created_at)`.

### `eval_results` (model `EvalResult`, `TimestampMixin`)

`id` (uuid pk) · `created_at` · `run_id` uuid NOT NULL FK → `eval_runs.id` `ON DELETE CASCADE` ·
`question` text NOT NULL · `question_class` text NULL · `persona` text NULL · `answerable` bool
NOT NULL · `expected_slugs` jsonb NOT NULL · `cited_slugs` jsonb NOT NULL · `slugs_hit` bool NOT
NULL · `fully_supported` bool NULL · `refused` bool NOT NULL · `verdict` text NOT NULL ·
`top_similarity` real NULL · `answer_text` text NOT NULL default `''` · **`metrics` jsonb NULL**
(tasks 05/06/07 write every extra metric here — no further migration).
Unique `uq_eval_results_run_id_question` on `(run_id, question)`; index `ix_eval_results_run_id`.

### `content_proposals` (model `ContentProposal`, `TimestampMixin` + `UpdatedAtMixin`)

`id` · `created_at` · `updated_at` · `kind` text NOT NULL CHECK `kind in ('new_article',
'expand_article', 'retune')` · `title` text NOT NULL · `rationale` text NOT NULL · `evidence`
jsonb NOT NULL · `target_content_id` uuid NULL FK → `content.id` · `draft_content_id` uuid NULL FK
→ `content.id` · `status` text NOT NULL default `'proposed'` CHECK `status in ('proposed',
'accepted', 'rejected')` · `eval_run_before_id` uuid NULL FK → `eval_runs.id` ·
`eval_run_after_id` uuid NULL FK → `eval_runs.id` · `created_by` uuid NULL FK → `users.id`.
Index `ix_content_proposals_status_created` on `(status, created_at)`.

> DESIGN gives `content_proposals` an `updated_at`, which PRD §4.1 scopes to `users`/`content`/
> `tags` only. DESIGN wins (it is authoritative on conflict); note it in the report.

### `chat_messages` additions

`feedback` smallint NULL, CHECK `ck_chat_messages_feedback_valid`: `feedback in (-1, 1)` ·
`latency_ms` integer NULL. Both nullable with no default — "never asked" ≠ "neutral".

### `app/services/chat.py`

```python
class RetrievedChunkLike(Protocol):
    ...
    @property
    def similarity(self) -> float: ...
```

`record_assistant_message(session, chat_session_id, text, retrieval, *, latency_ms: int | None = None)`
— keyword-only and defaulted, so every existing call site keeps working. Citation dicts gain one
key: `"similarity": round(chunk.similarity, 4)`. Readers must use `.get("similarity")` (pre-0009
rows have none).

### `app/routes/public_routes.py`

`_generate_chat_stream(session, chat_llm, embedder, settings, body, *, started_at: float)`;
`public_chat` passes `started_at=_start` (already captured at line 391). Immediately before
`record_assistant_message`, compute `latency_ms = int((time.monotonic() - started_at) * 1000)` and
pass it. This is whole-answer latency, deliberately not time-to-first-token (which
`_on_first_event` already tracks separately).

## Steps (TDD)

- [ ] **RED — test-author, 1/3.** Create `apps/api/tests/test_eval_models.py`:

```python
"""Schema pins for the phase-9 tables and the two new `chat_messages` signal columns."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ChatMessage, ChatSession, ContentProposal, EvalResult, EvalRun


def _run(session: Session, **overrides: object) -> EvalRun:
    values: dict[str, object] = {
        "label": "baseline",
        "embedding_model": "text-embedding-3-small",
        "chat_model": "gpt-4o-mini",
        "judge_model": "gpt-4o",
        "similarity_threshold": 0.5,
        "retrieval_k": 6,
        "corpus_content_count": 17,
        "corpus_chunk_count": 100,
        "corpus_max_updated_at": datetime.now(UTC),
        "corpus_digest": "0123456789abcdef",
        "total_questions": 21,
        "pct_fully_supported": 58.8,
        "refusal_correct": 4,
        "refusal_total": 4,
    }
    values.update(overrides)
    run = EvalRun(**values)  # type: ignore[arg-type]
    session.add(run)
    session.flush()
    return run


def test_eval_run_defaults_kind_answer_and_empty_git_sha(db_session: Session) -> None:
    run = _run(db_session)
    db_session.expire(run)
    assert run.kind == "answer"
    assert run.git_sha == ""
    assert isinstance(run.id, uuid.UUID)


def test_eval_run_kind_check_rejects_unknown_kind(db_session: Session) -> None:
    # `_run` flushes, so the CHECK violation surfaces from inside the helper.
    with pytest.raises(IntegrityError):
        _run(db_session, kind="bogus")
    db_session.rollback()


def test_eval_result_unique_per_run_and_question(db_session: Session) -> None:
    run = _run(db_session)
    for _ in range(2):
        db_session.add(
            EvalResult(
                run_id=run.id,
                question="What is a Roth IRA conversion and how is it taxed?",
                answerable=True,
                expected_slugs=["roth-ira-conversion-basics"],
                cited_slugs=["roth-ira-conversion-basics"],
                slugs_hit=True,
                fully_supported=True,
                refused=False,
                verdict="PASS",
                top_similarity=0.81,
                answer_text="It is a taxable event.",
            )
        )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_eval_result_metrics_jsonb_round_trips_and_cascades_with_its_run(
    db_session: Session,
) -> None:
    run = _run(db_session)
    db_session.add(
        EvalResult(
            run_id=run.id,
            question="q1",
            question_class="near_miss",
            persona="Sam",
            answerable=True,
            expected_slugs=[],
            cited_slugs=[],
            slugs_hit=False,
            fully_supported=None,
            refused=True,
            verdict="FAIL",
            top_similarity=None,
            answer_text="",
            metrics={"recall_at_k": 0.0, "failure_cause": "corpus_gap"},
        )
    )
    db_session.flush()
    stored = db_session.scalars(select(EvalResult)).one()
    assert stored.metrics == {"recall_at_k": 0.0, "failure_cause": "corpus_gap"}
    assert stored.question_class == "near_miss"

    db_session.delete(run)
    db_session.flush()
    assert db_session.scalars(select(EvalResult)).all() == []


def test_content_proposal_defaults_proposed_and_rejects_bad_kind(db_session: Session) -> None:
    proposal = ContentProposal(
        kind="new_article",
        title="RSUs for non-US employees",
        rationale="10 near-miss questions in 30 days",
        evidence={"weak_queries": []},
    )
    db_session.add(proposal)
    db_session.flush()
    db_session.expire(proposal)
    assert proposal.status == "proposed"
    assert isinstance(proposal.updated_at, datetime)

    db_session.add(
        ContentProposal(kind="bogus", title="t", rationale="r", evidence={})
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("value", [0, 2, -2])
def test_chat_message_feedback_check_rejects_values_other_than_minus_one_and_one(
    db_session: Session, value: int
) -> None:
    chat_session = ChatSession()
    db_session.add(chat_session)
    db_session.flush()
    db_session.add(
        ChatMessage(
            session_id=chat_session.id, role="assistant", content="a", feedback=value
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("value", [-1, 1, None])
def test_chat_message_feedback_accepts_minus_one_one_and_null(
    db_session: Session, value: int | None
) -> None:
    chat_session = ChatSession()
    db_session.add(chat_session)
    db_session.flush()
    message = ChatMessage(
        session_id=chat_session.id, role="assistant", content="a", feedback=value, latency_ms=1234
    )
    db_session.add(message)
    db_session.flush()
    db_session.expire(message)
    assert message.feedback == value
    assert message.latency_ms == 1234
```

- [ ] **RED — test-author, 2/3.** Create `apps/api/tests/test_migration_0009_roundtrip.py`:

```python
"""0009 round-trip: head -> 0008 -> head leaves a schema identical to the ORM metadata."""

from __future__ import annotations

import os
from pathlib import Path

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine

from app.models import Base

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
_ALEMBIC_SCRIPT_LOCATION = Path(__file__).resolve().parent.parent / "alembic"


def _alembic_config() -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
    url = os.environ["TEST_DATABASE_URL"]
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def _ignore_alembic_version_table(
    object_: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    return not (type_ == "table" and name == "alembic_version")


def test_0009_downgrades_to_0008_and_upgrades_back_to_a_matching_schema(
    tmp_engine: Engine,
) -> None:
    with tmp_engine.connect() as conn:
        schema = conn.execute(sa.text("SELECT current_schema()")).scalar_one()

    cfg = _alembic_config()
    previous = os.environ.get("MIGRATE_SCHEMA")
    os.environ["MIGRATE_SCHEMA"] = str(schema)
    try:
        downgrade(cfg, "0008")
        inspector = sa.inspect(tmp_engine)
        tables = set(inspector.get_table_names(schema=str(schema)))
        assert "eval_runs" not in tables
        assert "eval_results" not in tables
        assert "content_proposals" not in tables
        chat_columns = {c["name"] for c in inspector.get_columns("chat_messages", schema=str(schema))}
        assert "feedback" not in chat_columns
        assert "latency_ms" not in chat_columns

        upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("MIGRATE_SCHEMA", None)
        else:
            os.environ["MIGRATE_SCHEMA"] = previous

    with tmp_engine.connect() as conn:
        context = MigrationContext.configure(
            conn,
            opts={
                "compare_server_default": True,
                "include_object": _ignore_alembic_version_table,
            },
        )
        assert compare_metadata(context, Base.metadata) == []
```

- [ ] **RED — test-author, 3/3.** Edit `apps/api/tests/test_public_chat.py`:
  1. Replace `_chunk_level_citation` (lines 191-201) with:

```python
def _chunk_level_citation(
    content: Content, chunk: Chunk, similarity: float
) -> dict[str, object]:
    """The chunk-level DB shape PRD §4 pins for the persisted assistant row's `citations` column.

    Phase-9 DESIGN §A: each entry now also carries the retriever's own `similarity` (rounded to
    4 dp), so every stored answer is a retrieval trace. Compared with `pytest.approx` because the
    value comes back through pgvector's float arithmetic.
    """
    return {
        "content_id": str(content.id),
        "title": content.title,
        "slug": content.slug,
        "chunk_id": str(chunk.id),
        "similarity": pytest.approx(similarity, abs=1e-3),
    }
```

  2. In `test_citation_asymmetry_wire_deduped_content_level_row_chunk_level_from_one_exchange`
     (lines 462-464), pass each chunk's scripted cosine:
     `_chunk_level_citation(content_a, chunk_a1, 0.9)`,
     `_chunk_level_citation(content_b, chunk_b1, 0.7)`,
     `_chunk_level_citation(content_a, chunk_a2, 0.5)`.
  3. Append this new test at the end of the file:

```python
def test_assistant_row_records_latency_ms_for_the_exchange(
    tmp_engine: Engine, db_session: Session
) -> None:
    """Phase-9 DESIGN §A: `latency_ms` comes from the route's own monotonic clock."""
    content = _add_content(db_session, slug="latency-content")
    _add_chunk(db_session, content.id, chunk_index=0, text="latency chunk", cos_theta=0.9)
    db_session.commit()

    client = _build_client(
        tmp_engine,
        chat_llm=FakeChatLLM(answer_tokens=["Grounded ", "answer."]),
        embedder=FakeEmbedder(vector=QUERY_VECTOR),
    )
    status, _content_type, body = _post_chat(client, {"message": "How long did that take?"})
    assert status == 200, body

    events = _parse_sse_events(body)
    done_event = next(e for e in events if e.name == "done")
    message_id = uuid.UUID(str(done_event.data["message_id"]))

    with make_session_factory(tmp_engine)() as fresh:
        assistant_row = fresh.get(ChatMessage, message_id)
        assert assistant_row is not None
        assert assistant_row.latency_ms is not None
        assert 0 <= assistant_row.latency_ms < 60_000
        assert assistant_row.feedback is None
```

- [ ] **Run RED:** `cd apps/api && TEST_DATABASE_URL=… uv run pytest tests/test_eval_models.py
  tests/test_migration_0009_roundtrip.py tests/test_public_chat.py -q` → the new/edited tests FAIL
  (`ImportError: cannot import name 'EvalRun'`, missing columns, `KeyError: 'similarity'`). Paste
  the failure lines into the test-author report.

- [ ] **GREEN — implementer.** Write `app/models/eval.py` exactly per Interfaces (module
  docstring citing DESIGN §B1/§D), register the three models in `app/models/__init__.py` (imports
  + `__all__`, alphabetical), add the two `chat_messages` columns + CHECK, then hand-write
  `alembic/versions/0009_eval_and_feedback.py` (`revision = "0009"`, `down_revision = "0008"`).
  Order in `upgrade()`: the two `chat_messages` columns + `op.create_check_constraint(
  op.f("ck_chat_messages_feedback_valid"), "chat_messages", "feedback in (-1, 1)")`, then
  `eval_runs`, `eval_results` (FK → `eval_runs`), `content_proposals` (FKs → `content`,
  `eval_runs`, `users`) plus their indexes. `downgrade()` reverses exactly: drop
  `content_proposals`, `eval_results`, `eval_runs` (indexes first, per 0007's shape), drop the
  CHECK, then the two columns. Use `sa.UUID()`, `postgresql.JSONB(astext_type=sa.Text())`,
  `sa.REAL()`, `sa.SmallInteger()`, `sa.Float()` and `op.f()` names as in 0001/0007.
  Then the two writer changes (`app/services/chat.py`, `app/routes/public_routes.py`) per
  Interfaces.

- [ ] **Run GREEN:** the three files above, then `uv run pytest -q` (whole suite — the parity gate
  `tests/test_models_schema.py::test_orm_metadata_matches_migration_head` must be green, and
  `tests/test_content_gaps.py`/`tests/test_public_chat_txn.py` must not regress).

- [ ] **Gates:** `pnpm gates:api` (ruff, ruff format, mypy, **lint-imports**, pytest) → clean.
  `git diff --exit-code -- apps/api/openapi.json apps/api/mcp-tools.json` must PASS (no wire move).

- [ ] **Commit:**
  `git commit -m "feat(api): migration 0009 — eval tables, feedback/latency signals, citation similarity (p9 t01)"`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=$(grep -m1 '^TEST_DATABASE_URL=' ../../.env | cut -d= -f2-) \
  uv run pytest tests/test_eval_models.py tests/test_migration_0009_roundtrip.py \
  tests/test_models_schema.py tests/test_public_chat.py -q
pnpm gates:api
git diff --exit-code -- apps/api/openapi.json apps/api/mcp-tools.json   # must pass
```

## Acceptance

- `uv run alembic upgrade head` → `downgrade 0008` → `upgrade head` leaves a schema that
  `compare_metadata(..., compare_server_default=True)` finds identical to `Base.metadata`.
- Every constraint/index name in 0009 matches what `Base.metadata`'s naming convention produces
  (parity gate green, not just "tests pass").
- `feedback` rejects 0/2/-2 and accepts -1/1/NULL; `eval_runs.kind` defaults to `'answer'` and
  rejects anything else; `(run_id, question)` is unique; deleting an `EvalRun` cascades its
  results; `eval_results.metrics` round-trips arbitrary JSON.
- Every persisted assistant citation carries `similarity` (4 dp); the wire `citations` event is
  unchanged (still `{content_id, title, slug}`); `latency_ms` is populated on every successful
  exchange and stays NULL on the error path.
- `openapi.json`, `mcp-tools.json`, and both `schema.d.ts` are byte-identical to `main`.

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-01-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-01-implementer.md`
