"""Fix round 1 (Opus review of commit 08dd82a) — covering tests for C2, I2, I3, I4, I5.

Review: `.superpowers/sdd/reports/p5-t01-review.md`. This file is NEW (not a pinned test file);
it exercises `app.mcp.runtime.call_tool` (the in-process seam, unaffected by any of these fixes —
its documented contract of raising `ToolNotFoundError`/`ToolInputError`/whatever a tool's own
service call raises is intentionally untouched) AND `app.mcp.server._execute_tool_call` (the
synchronous span the HTTP transport now offloads to a worker thread — see
`tests/test_mcp_http_transport.py` for the offloading/concurrency evidence itself; this file
covers what `_execute_tool_call` decides once it runs).

Findings covered here:
  - I4: `search_content`'s `limit` now has domain bounds (`ge=1, le=100`) — bad values raise
    `ToolInputError` naming `limit` instead of escaping to an unhandled `DataError`/returning an
    unbounded or empty result silently.
  - I5: both read tools' args models now set `extra="forbid"` — an unknown/misspelled argument
    raises `ToolInputError` naming that field instead of being silently dropped.
  - I3: a business error (`NotFoundError`/`ConflictError`, not just `ToolNotFoundError`/
    `ToolInputError`) raised by a tool's handler is converted to a structured, in-band
    `CallToolResult(is_error=True)` by `app.mcp.server._execute_tool_call` — proven through the
    real registration path (`app.mcp.runtime.call_tool`'s own registry, `monkeypatch`-extended
    with a temporary tool, exactly the shape task-02's write tools will use).
  - C2: a tool handler that flushes a write and then fails leaves nothing committed —
    `_execute_tool_call` rolls back before returning the in-band error.
  - I2: an unexpected (non-`AppError`) exception's detail (here: fabricated SQL-looking text) never
    reaches the client-visible `CallToolResult`; the client gets a fixed generic message, and the
    real detail is logged server-side (`caplog`).

CONVENTIONS.md §10: DB-touching tests request `db_session`/`tmp_engine` and are skipped by fixture
name when `TEST_DATABASE_URL` is unset (see `tests/conftest.py`).
"""

from __future__ import annotations

import logging
import uuid

import pytest
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

import app.mcp.runtime as runtime_module
from app.db import make_session_factory
from app.mcp.runtime import call_tool
from app.mcp.server import _execute_tool_call
from app.mcp.tool_spec import ToolSpec
from app.models import Content, User
from app.services import content as content_service
from app.services.errors import ConflictError, NotFoundError, ToolInputError


@pytest.fixture
def actor_id(tmp_engine: Engine) -> uuid.UUID:
    """A seeded `User` row's id, COMMITTED (unlike the pinned `test_mcp_read_tools.py::actor_id`
    fixture, which only flushes on `db_session`). Several tests below (`_execute_tool_call`'s own
    tests) open a session that is NOT `db_session` — a separate connection against the same
    `tmp_engine`, exactly like the real HTTP transport does — so the actor row must actually be
    committed to be visible across that connection boundary, or every `Content.author_id`/
    `updated_by` foreign key insert fails."""
    session_factory = make_session_factory(tmp_engine)
    session = session_factory()
    try:
        user = User(email="guard-tests-admin@example.com", name="Guard Tests Admin")
        session.add(user)
        session.commit()
        return user.id
    finally:
        session.close()


# ---------------------------------------------------------------------------
# I4 — search_content's `limit` domain bounds
# ---------------------------------------------------------------------------


def test_search_content_negative_limit_raises_tool_input_error_naming_field(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`limit=-1` no longer escapes to an unhandled `DataError` — it's a `ToolInputError`."""
    with pytest.raises(ToolInputError) as exc_info:
        call_tool("search_content", {"limit": -1}, session=db_session, actor_id=actor_id)

    assert "limit" in str(exc_info.value)


def test_search_content_zero_limit_raises_tool_input_error_naming_field(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`limit=0` previously silently returned `{items: [], count: N}` — now rejected up front."""
    with pytest.raises(ToolInputError) as exc_info:
        call_tool("search_content", {"limit": 0}, session=db_session, actor_id=actor_id)

    assert "limit" in str(exc_info.value)


def test_search_content_limit_above_cap_raises_tool_input_error_naming_field(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`limit=101` (above the disclosed cap of 100) is rejected, not silently accepted."""
    with pytest.raises(ToolInputError) as exc_info:
        call_tool("search_content", {"limit": 101}, session=db_session, actor_id=actor_id)

    assert "limit" in str(exc_info.value)


def test_search_content_limit_at_cap_is_accepted(db_session: Session, actor_id: uuid.UUID) -> None:
    """The cap itself (100) is a valid value, not an off-by-one rejection."""
    result = call_tool("search_content", {"limit": 100}, session=db_session, actor_id=actor_id)

    assert result["items"] == []
    assert result["count"] == 0


# ---------------------------------------------------------------------------
# I5 — unknown/misspelled arguments
# ---------------------------------------------------------------------------


def test_search_content_unknown_argument_raises_tool_input_error_naming_field(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """A misspelled `query` (meant `q`) is no longer silently dropped (which previously returned
    every row instead of the intended filtered set) — `extra="forbid"` rejects it by name."""
    with pytest.raises(ToolInputError) as exc_info:
        call_tool("search_content", {"query": "Item"}, session=db_session, actor_id=actor_id)

    assert "query" in str(exc_info.value)


def test_search_content_misspelled_limit_raises_tool_input_error_naming_field(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    with pytest.raises(ToolInputError) as exc_info:
        call_tool("search_content", {"limitt": 2}, session=db_session, actor_id=actor_id)

    assert "limitt" in str(exc_info.value)


def test_count_content_unknown_argument_raises_tool_input_error_naming_field(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    with pytest.raises(ToolInputError) as exc_info:
        call_tool("count_content", {"nonsense": 1}, session=db_session, actor_id=actor_id)

    assert "nonsense" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Shared scaffolding for I3/C2/I2: a temporary tool registered the same way task-02's write
# tools will be (a `ToolSpec` in `app.mcp.runtime`'s registry), so these tests exercise the real
# registration path rather than calling `_execute_tool_call`'s internals directly with a bespoke
# shape.
# ---------------------------------------------------------------------------

_ROLLBACK_PROBE_TITLE = "MCP C2 rollback probe — should never be committed"


class _EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _register_temp_tool(monkeypatch: pytest.MonkeyPatch, spec: ToolSpec) -> None:
    """Add `spec` to `app.mcp.runtime`'s live registry for the duration of one test.

    Mutates the same `dict` object `call_tool`/`_execute_tool_call` read (not a rebound module
    attribute), so this is visible to both immediately; `monkeypatch` restores the registry on
    teardown regardless of pass/fail.
    """
    monkeypatch.setitem(runtime_module._REGISTRY, spec.name, spec)


# ---------------------------------------------------------------------------
# I3 — business errors (NotFoundError/ConflictError) surface as in-band structured tool errors
# ---------------------------------------------------------------------------


def test_service_not_found_error_propagates_raw_through_call_tool_seam(
    db_session: Session, actor_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The in-process seam (`call_tool`, what task-03's agent loop calls directly) is untouched by
    the I3 fix — it still raises the real `NotFoundError`, exactly as any other service caller
    would see it. The in-band-conversion behavior belongs to the MCP transport layer
    (`_execute_tool_call`/`_handle_call_tool`), not to `runtime.call_tool` itself — proven here by
    the absence of any conversion at this seam."""

    def _handler(args: _EmptyArgs, *, session: Session, actor_id: uuid.UUID) -> dict[str, object]:
        raise NotFoundError("simulated not-found from a registered tool")

    _register_temp_tool(
        monkeypatch,
        ToolSpec(
            name="_test_raises_not_found",
            description="test-only",
            args_model=_EmptyArgs,
            handler=_handler,
        ),
    )

    with pytest.raises(NotFoundError):
        call_tool("_test_raises_not_found", {}, session=db_session, actor_id=actor_id)


def test_service_not_found_error_surfaces_as_in_band_structured_tool_error(
    tmp_engine: Engine, actor_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The MCP HTTP transport layer (`_execute_tool_call`, called by `_handle_call_tool` for every
    `tools/call`) converts the SAME `NotFoundError` into an in-band `CallToolResult(is_error=True)`
    carrying `{code: "not_found", message: ...}` — PRD §6's self-correction contract. This is the
    exact failure scenario the review's I3 finding describes for task-02's `archive` tool hitting a
    `ConflictError`/`NotFoundError`, generalized here to `NotFoundError` via a temp tool registered
    through the real registry (the same mechanism task-02's write tools use)."""

    def _handler(args: _EmptyArgs, *, session: Session, actor_id: uuid.UUID) -> dict[str, object]:
        raise NotFoundError("simulated not-found from a registered tool")

    _register_temp_tool(
        monkeypatch,
        ToolSpec(
            name="_test_raises_not_found",
            description="test-only",
            args_model=_EmptyArgs,
            handler=_handler,
        ),
    )

    result = _execute_tool_call(
        make_session_factory(tmp_engine), "_test_raises_not_found", {}, actor_id
    )

    assert result.is_error is True
    text = result.content[0].text  # type: ignore[union-attr]
    assert "not_found" in text
    assert "simulated not-found from a registered tool" in text


def test_service_conflict_error_surfaces_as_in_band_structured_tool_error(
    tmp_engine: Engine, actor_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same as above for `ConflictError` — the review's own failure scenario (`archive_content`
    raising `ConflictError` on a non-published item)."""

    def _handler(args: _EmptyArgs, *, session: Session, actor_id: uuid.UUID) -> dict[str, object]:
        raise ConflictError("Cannot archive content with status 'draft'.")

    _register_temp_tool(
        monkeypatch,
        ToolSpec(
            name="_test_raises_conflict",
            description="test-only",
            args_model=_EmptyArgs,
            handler=_handler,
        ),
    )

    result = _execute_tool_call(
        make_session_factory(tmp_engine), "_test_raises_conflict", {}, actor_id
    )

    assert result.is_error is True
    text = result.content[0].text  # type: ignore[union-attr]
    assert "conflict" in text
    assert "Cannot archive content with status 'draft'." in text


# ---------------------------------------------------------------------------
# C2 — a flushed-then-failed write is rolled back, not committed
# ---------------------------------------------------------------------------


def test_flush_then_fail_tool_rolls_back_the_flushed_write(
    tmp_engine: Engine, actor_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """This is the review's own C2 failure scenario, reproduced directly: a tool handler flushes a
    write (mirroring `content_service.update_content`'s `_replace_tags` deleting rows and
    `flush()`ing before a later step can still fail) and then raises. Before the fix,
    `_AdminGatedMcpApp.__call__` committed unconditionally whenever `manager.handle_request`
    returned without raising — which it always does, since the SDK swallows handler exceptions
    into a JSON-RPC error response. After the fix, `_execute_tool_call` rolls back BEFORE
    returning, because it makes the commit/rollback decision itself, in-band, rather than relying
    on an exception it will never see propagate."""

    def _handler(args: _EmptyArgs, *, session: Session, actor_id: uuid.UUID) -> dict[str, object]:
        content_service.create_draft(session, title=_ROLLBACK_PROBE_TITLE, actor_id=actor_id)
        raise ConflictError("simulated failure after a flushed write")

    _register_temp_tool(
        monkeypatch,
        ToolSpec(
            name="_test_flush_then_fail",
            description="test-only",
            args_model=_EmptyArgs,
            handler=_handler,
        ),
    )

    session_factory = make_session_factory(tmp_engine)
    result = _execute_tool_call(session_factory, "_test_flush_then_fail", {}, actor_id)

    assert result.is_error is True

    # A fresh session (never touched by the tool call above) sees NOTHING — proving the flushed
    # `Content` row was rolled back, not partially committed.
    verify_session = session_factory()
    try:
        rows = (
            verify_session.execute(select(Content).where(Content.title == _ROLLBACK_PROBE_TITLE))
            .scalars()
            .all()
        )
        assert rows == []
    finally:
        verify_session.close()


def test_successful_tool_call_commits(
    tmp_engine: Engine, actor_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Companion to the rollback test above: a handler that flushes and does NOT raise gets its
    write committed — proving the fix didn't turn every call into a rollback."""
    title = "MCP C2 commit probe — should be committed"

    def _handler(args: _EmptyArgs, *, session: Session, actor_id: uuid.UUID) -> dict[str, object]:
        content = content_service.create_draft(session, title=title, actor_id=actor_id)
        return {"id": str(content.id)}

    _register_temp_tool(
        monkeypatch,
        ToolSpec(
            name="_test_flush_then_succeed",
            description="test-only",
            args_model=_EmptyArgs,
            handler=_handler,
        ),
    )

    session_factory = make_session_factory(tmp_engine)
    result = _execute_tool_call(session_factory, "_test_flush_then_succeed", {}, actor_id)

    assert result.is_error is False

    verify_session = session_factory()
    try:
        rows = verify_session.execute(select(Content).where(Content.title == title)).scalars().all()
        assert len(rows) == 1
    finally:
        verify_session.close()


# ---------------------------------------------------------------------------
# I2 — unexpected exceptions never leak internal detail to the client
# ---------------------------------------------------------------------------


def test_unexpected_exception_is_sanitized_for_the_client_but_logged_in_full(
    tmp_engine: Engine,
    actor_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A tool handler raising something other than `AppError` (here: simulating the SQL-leak the
    review's probe P7 measured — `DataError`'s `str()` embeds the statement and bind parameters)
    must not hand that detail to the MCP client. The client-visible result is a fixed generic
    message; the real detail reaches the server log only (`app/routes/errors.py`'s
    `_unhandled_exception_handler` established this "never `str(exc)` to the caller" invariant for
    REST — this proves the MCP transport now honors it too)."""
    _leaked_detail = (
        "SELECT content.id, content.title FROM content WHERE content.is_deleted IS false "
        "ORDER BY content.created_at [parameters: {'param_1': -1, 'param_2': 0}]"
    )

    def _handler(args: _EmptyArgs, *, session: Session, actor_id: uuid.UUID) -> dict[str, object]:
        raise RuntimeError(_leaked_detail)

    _register_temp_tool(
        monkeypatch,
        ToolSpec(
            name="_test_raises_unexpected",
            description="test-only",
            args_model=_EmptyArgs,
            handler=_handler,
        ),
    )

    with caplog.at_level(logging.ERROR, logger="app.mcp.server"):
        result = _execute_tool_call(
            make_session_factory(tmp_engine), "_test_raises_unexpected", {}, actor_id
        )

    assert result.is_error is True
    client_text = result.content[0].text  # type: ignore[union-attr]
    assert "SELECT" not in client_text
    assert "param_1" not in client_text
    assert _leaked_detail not in client_text
    assert "internal_error" in client_text
    assert "Internal server error." in client_text

    # The real detail DID reach the server log — sanitizing the client response must not mean
    # silently swallowing the failure server-side too. `caplog.text` (not `record.getMessage()`,
    # which excludes the formatted traceback) is where `logger.exception`'s `exc_info` output
    # lands — the `RuntimeError`'s message (the fabricated SQL detail) is part of that traceback.
    assert _leaked_detail in caplog.text
