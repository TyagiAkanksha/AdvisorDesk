"""Failing (RED) tests for `report_content_gaps` — the ninth MCP tool (phase-7 task-01).

Task brief: .superpowers/sdd/phase-7-evaluation/task-01-brief.md, Steps 1 and 5.
Spec: advisordesk-prd.md §6 `report_content_gaps` row (query definition, normative): "user
messages whose following assistant message (same session, next by `created_at`) has
`retrieval_found = false`", last `days` days, newest first, `{count, gaps:[{question, asked_at,
session_id}]}`.

CONTROLLER RULING D (registration seam — the brief's "Modify app/mcp/server.py (register)" line
is stale): each tool is a `ToolSpec` collected into `app.mcp.runtime._ALL_TOOLS`, mirroring
`app.mcp.tools_read.READ_TOOLS` / `app.mcp.tools_write.WRITE_TOOLS`. Tool-level tests below go
through `app.mcp.runtime.call_tool` directly — the exact seam `tests/test_mcp_read_tools.py`
uses (no `TestClient`, no HTTP).

Neither `app.services.chat.content_gaps` nor the MCP tool `report_content_gaps` exist yet: the
very first import below (`from app.services.chat import content_gaps`) is expected to fail at
collection with `ImportError: cannot import name 'content_gaps' from 'app.services.chat'` until
the implementer (a separate agent) adds the query function (Step 3) and registers the tool
(Step 6). That `ImportError` IS the RED evidence this file exists to produce — every test in
this module fails at collection until both exist, mirroring `test_mcp_read_tools.py`'s own
documented collection-time-failure pattern for a not-yet-created symbol.

Seeding: `ChatMessage`/`ChatSession` rows are constructed directly via the ORM (not through
`app.services.chat.record_user_message`/`record_assistant_message`, which don't accept an
explicit `created_at`) — this suite needs exact, caller-chosen `created_at` values to pin the
§6 pairing/window/ordering semantics deterministically. `TimestampMixin.created_at` is a plain
`mapped_column` with only a `server_default` (`app/models/base.py`), so passing `created_at=`
explicitly on construction is honored verbatim (the server default only applies when the
column is left unset).

CONVENTIONS.md §10: DB tests run against a throwaway Postgres schema when `TEST_DATABASE_URL`
is set, and are skipped by fixture name otherwise
(`tests/conftest.py::pytest_collection_modifyitems`) — every test here requests `db_session`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.mcp.runtime import call_tool
from app.models import ChatMessage, ChatSession, User
from app.services.chat import content_gaps
from app.services.errors import ToolInputError

# ---------------------------------------------------------------------------
# Shared seeding helpers (test-only; not imported from any other test file,
# per this suite's own no-cross-test-file-dependency precedent —
# `tests/test_mcp_read_tools.py`'s `actor_id` fixture docstring).
# ---------------------------------------------------------------------------


@pytest.fixture
def actor_id(db_session: Session) -> uuid.UUID:
    """A seeded `User` row's id — the `actor_id` `call_tool` takes (PRD §4.1)."""
    user = User(email="admin@example.com", name="Test Admin")
    db_session.add(user)
    db_session.flush()
    return user.id


def _add_session(session: Session) -> ChatSession:
    chat_session = ChatSession()
    session.add(chat_session)
    session.flush()
    return chat_session


def _add_message(
    session: Session,
    chat_session_id: uuid.UUID,
    *,
    role: str,
    content: str,
    created_at: datetime,
    retrieval_found: bool | None = None,
) -> ChatMessage:
    """Seed one `chat_messages` row with an explicit `created_at` (see module docstring)."""
    message = ChatMessage(
        session_id=chat_session_id,
        role=role,
        content=content,
        created_at=created_at,
        retrieval_found=retrieval_found,
    )
    session.add(message)
    session.flush()
    return message


# ---------------------------------------------------------------------------
# Step 1: `content_gaps` query semantics (§6).
# ---------------------------------------------------------------------------


def test_user_message_followed_by_uncovered_reply_is_a_gap(db_session: Session) -> None:
    """A user msg whose next assistant reply has `retrieval_found=False` is included."""
    chat_session = _add_session(db_session)
    now = datetime.now(UTC)
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="What is a backdoor Roth conversion?",
        created_at=now,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="assistant",
        content="I don't have guidance on that.",
        created_at=now + timedelta(seconds=1),
        retrieval_found=False,
    )

    gaps = content_gaps(db_session, days=30, limit=20)

    assert len(gaps) == 1
    assert gaps[0].question == "What is a backdoor Roth conversion?"
    assert gaps[0].session_id == chat_session.id
    assert gaps[0].asked_at == now


def test_user_message_followed_by_covered_reply_is_excluded(db_session: Session) -> None:
    """A user msg whose next assistant reply has `retrieval_found=True` is excluded."""
    chat_session = _add_session(db_session)
    now = datetime.now(UTC)
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="What is a Roth IRA?",
        created_at=now,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="assistant",
        content="A Roth IRA is a tax-advantaged retirement account.",
        created_at=now + timedelta(seconds=1),
        retrieval_found=True,
    )

    gaps = content_gaps(db_session, days=30, limit=20)

    assert gaps == []


def test_pairing_pins_each_user_message_to_its_own_next_assistant_reply(
    db_session: Session,
) -> None:
    """§6 pairing pin: two user messages in one session each pair with their OWN next
    assistant message — interleaving must not cross-pair.

    Timeline (by `created_at`): U1(covered) -> A1(true) -> U2(uncovered) -> A2(false).
    Correct pairing: U1<->A1 (excluded), U2<->A2 (included) — a buggy implementation that
    treats "any assistant row in this session has retrieval_found=false" as grounds to
    include every user message in the session would wrongly include U1 too.

    Rows are inserted OUT of chronological order (A2 first, U2 last) while `created_at`
    values are set to the logical timeline above — this forces a correct implementation to
    order by the `created_at` column (the §6-normative "next by `created_at`"), not by
    insertion order or primary-key generation order.
    """
    chat_session = _add_session(db_session)
    now = datetime.now(UTC)
    t_u1 = now
    t_a1 = now + timedelta(seconds=1)
    t_u2 = now + timedelta(seconds=2)
    t_a2 = now + timedelta(seconds=3)

    # Deliberately shuffled insertion order — see docstring.
    _add_message(
        db_session,
        chat_session.id,
        role="assistant",
        content="Q2 answer (uncovered).",
        created_at=t_a2,
        retrieval_found=False,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="Q1: covered question",
        created_at=t_u1,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="assistant",
        content="Q1 answer (covered).",
        created_at=t_a1,
        retrieval_found=True,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="Q2: uncovered question",
        created_at=t_u2,
    )

    gaps = content_gaps(db_session, days=30, limit=20)

    assert [gap.question for gap in gaps] == ["Q2: uncovered question"]


def test_pairing_pins_reversed_outcome_order_too(db_session: Session) -> None:
    """Same pairing pin as above, outcomes reversed: uncovered first, covered second —
    guards against an implementation that only happens to work when the gap is the LAST
    exchange in the session.
    """
    chat_session = _add_session(db_session)
    now = datetime.now(UTC)
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="Q3: uncovered question",
        created_at=now,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="assistant",
        content="Q3 answer (uncovered).",
        created_at=now + timedelta(seconds=1),
        retrieval_found=False,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="Q4: covered question",
        created_at=now + timedelta(seconds=2),
    )
    _add_message(
        db_session,
        chat_session.id,
        role="assistant",
        content="Q4 answer (covered).",
        created_at=now + timedelta(seconds=3),
        retrieval_found=True,
    )

    gaps = content_gaps(db_session, days=30, limit=20)

    assert [gap.question for gap in gaps] == ["Q3: uncovered question"]


def test_user_message_with_no_following_assistant_reply_is_excluded(db_session: Session) -> None:
    """A user message with no following assistant message at all is never a gap."""
    chat_session = _add_session(db_session)
    now = datetime.now(UTC)
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="Answered question",
        created_at=now,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="assistant",
        content="No guidance found.",
        created_at=now + timedelta(seconds=1),
        retrieval_found=False,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="Unanswered question",
        created_at=now + timedelta(seconds=2),
    )

    gaps = content_gaps(db_session, days=30, limit=20)

    assert [gap.question for gap in gaps] == ["Answered question"]


def test_lone_user_messages_with_no_assistant_rows_never_appear_as_gaps(
    db_session: Session,
) -> None:
    """§6 pin: user rows (role `user`, `retrieval_found` NULL) never appear as gaps
    themselves. A session with ONLY user rows (no assistant row at all, so
    `retrieval_found` is NULL everywhere) must return zero gaps — guards against a query
    that treats `retrieval_found IS NOT TRUE` (which NULL also satisfies) as "uncovered".
    """
    chat_session = _add_session(db_session)
    now = datetime.now(UTC)
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="Solo question one",
        created_at=now,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="Solo question two",
        created_at=now + timedelta(seconds=1),
    )

    gaps = content_gaps(db_session, days=30, limit=20)

    assert gaps == []


def test_user_message_followed_by_null_retrieval_found_reply_is_excluded(
    db_session: Session,
) -> None:
    """Fix round 1 (Important finding): NULL `retrieval_found` must NOT count as false —
    pinned against a REAL paired assistant reply this time, not an absent one.

    `test_lone_user_messages_with_no_assistant_rows_never_appear_as_gaps` above seeds ZERO
    assistant rows, so its user messages are excluded by the pairing JOIN itself before the
    `retrieval_found` predicate is ever reached — `.is_(False)` and `.isnot(True)` both pass
    that test identically, so it can't catch a regression from one to the other. This test
    seeds a real assistant reply (same session, next by `created_at`) with `retrieval_found`
    explicitly `None` (via `_add_message`'s default), so the pairing JOIN succeeds and the
    `retrieval_found` predicate is the only thing standing between this row and being (wrongly)
    reported as a gap. With `.isnot(True)` in place of `.is_(False)`, NULL satisfies
    `isnot(True)` too, and this test fails.
    """
    chat_session = _add_session(db_session)
    now = datetime.now(UTC)
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="Question with an unset outcome",
        created_at=now,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="assistant",
        content="Reply with unset retrieval_found.",
        created_at=now + timedelta(seconds=1),
        # retrieval_found intentionally omitted -> None (see _add_message's default).
    )

    gaps = content_gaps(db_session, days=30, limit=20)

    assert gaps == []


def test_days_window_excludes_rows_older_than_cutoff(db_session: Session) -> None:
    """`days` bounds the window: a gap older than the cutoff is excluded, one inside it
    is kept."""
    chat_session = _add_session(db_session)
    now = datetime.now(UTC)

    old_asked_at = now - timedelta(days=40)
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="Old uncovered question",
        created_at=old_asked_at,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="assistant",
        content="No guidance (old).",
        created_at=old_asked_at + timedelta(seconds=1),
        retrieval_found=False,
    )

    recent_asked_at = now - timedelta(days=5)
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="Recent uncovered question",
        created_at=recent_asked_at,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="assistant",
        content="No guidance (recent).",
        created_at=recent_asked_at + timedelta(seconds=1),
        retrieval_found=False,
    )

    gaps = content_gaps(db_session, days=30, limit=20)

    assert [gap.question for gap in gaps] == ["Recent uncovered question"]


def test_gaps_ordered_newest_first(db_session: Session) -> None:
    """Gaps come back newest-first by `asked_at`."""
    chat_session = _add_session(db_session)
    now = datetime.now(UTC)

    offsets_days = [3, 1, 2]  # inserted out of chronological order on purpose
    for i, days_ago in enumerate(offsets_days):
        asked_at = now - timedelta(days=days_ago)
        _add_message(
            db_session,
            chat_session.id,
            role="user",
            content=f"Question {days_ago}d ago",
            created_at=asked_at,
        )
        _add_message(
            db_session,
            chat_session.id,
            role="assistant",
            content=f"No guidance {i}.",
            created_at=asked_at + timedelta(seconds=1),
            retrieval_found=False,
        )

    gaps = content_gaps(db_session, days=30, limit=20)

    assert [gap.question for gap in gaps] == [
        "Question 1d ago",
        "Question 2d ago",
        "Question 3d ago",
    ]


def test_limit_bounds_number_of_gaps_returned(db_session: Session) -> None:
    """`limit` truncates the (newest-first) result set."""
    chat_session = _add_session(db_session)
    now = datetime.now(UTC)

    for days_ago in [4, 3, 2, 1]:
        asked_at = now - timedelta(days=days_ago)
        _add_message(
            db_session,
            chat_session.id,
            role="user",
            content=f"Question {days_ago}d ago",
            created_at=asked_at,
        )
        _add_message(
            db_session,
            chat_session.id,
            role="assistant",
            content="No guidance.",
            created_at=asked_at + timedelta(seconds=1),
            retrieval_found=False,
        )

    gaps = content_gaps(db_session, days=30, limit=2)

    assert [gap.question for gap in gaps] == ["Question 1d ago", "Question 2d ago"]


# ---------------------------------------------------------------------------
# Step 5: `report_content_gaps` MCP tool — happy path + failure path (§9 floor).
# ---------------------------------------------------------------------------


def test_report_content_gaps_tool_happy_path_returns_count_and_gaps_with_iso_asked_at(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`call_tool("report_content_gaps", ...)` -> `{count, gaps:[{question, asked_at,
    session_id}]}` with `asked_at` as an ISO-8601 string (the HTTP transport `json.dumps`s
    this payload directly — see `app.mcp.tools_write._publish`'s `published_at` precedent).
    """
    chat_session = _add_session(db_session)
    now = datetime.now(UTC)
    _add_message(
        db_session,
        chat_session.id,
        role="user",
        content="What about backdoor Roth conversions?",
        created_at=now,
    )
    _add_message(
        db_session,
        chat_session.id,
        role="assistant",
        content="I don't have guidance on that.",
        created_at=now + timedelta(seconds=1),
        retrieval_found=False,
    )

    result = call_tool("report_content_gaps", {}, session=db_session, actor_id=actor_id)

    assert result["count"] == 1
    assert len(result["gaps"]) == 1
    gap = result["gaps"][0]
    assert set(gap.keys()) == {"question", "asked_at", "session_id"}
    assert gap["question"] == "What about backdoor Roth conversions?"
    assert gap["session_id"] == str(chat_session.id)
    assert isinstance(gap["asked_at"], str)
    # ISO-8601 round-trip, and equal to the exact seeded timestamp.
    assert datetime.fromisoformat(gap["asked_at"]) == now


def test_report_content_gaps_tool_rejects_negative_days_with_tool_input_error(
    db_session: Session, actor_id: uuid.UUID
) -> None:
    """`days=-1` -> `ToolInputError` (§9 failure-path floor: one per tool)."""
    with pytest.raises(ToolInputError):
        call_tool("report_content_gaps", {"days": -1}, session=db_session, actor_id=actor_id)
