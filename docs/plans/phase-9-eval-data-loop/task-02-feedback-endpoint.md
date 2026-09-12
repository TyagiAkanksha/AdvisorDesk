---
id: p9-t02
phase: phase-9-eval-data-loop
depends_on: [p9-t01]
status: todo
spec: docs/plans/phase-9-eval-data-loop/DESIGN.md
review: sonnet
---

# Task 02 — `POST /public/chat/{message_id}/feedback` (the only human signal)

## Goal

A client can send 👍/👎 on one assistant answer: `POST /api/v1/public/chat/{message_id}/feedback`
with `{"value": -1}` or `{"value": 1}` writes `chat_messages.feedback` (the column task 01 added)
and answers `204`. Unknown message id, or an id that names a `role='user'` row, answers `404`;
any other `value` answers `422`. No wire change is needed on the chat stream itself — the `done`
SSE event already carries `message_id` (`app/routes/public_routes.py:253-255`); the client types
and discards it today. `openapi.json` and both apps' generated types are regenerated in the same
commit (CONVENTIONS.md §8).

## Context (read ONLY these)

- `docs/plans/phase-9-eval-data-loop/DESIGN.md` §"Part A" (the `feedback` row) and D2.
- `CONVENTIONS.md` §4 (no `try/except` in routes — `NotFoundError` flows to the handlers), §5
  (explicit stable `operation_id`), §8 (baselines + both codegens in the same commit), §10.
- `apps/api/app/routes/public_routes.py` — the whole file; in particular the router construction
  (line 94), `_DETAIL_RESPONSES` (line 98) and `public_content_get` (lines 136-157) as the
  shape to mirror for a 404-bearing public route.
- `apps/api/app/routes/content_routes.py:194-211` — the 204 route idiom (`status_code=204` on the
  decorator, `return Response(status_code=204)`).
- `apps/api/app/routes/deps.py:26-56` — `get_session` commits on success, rolls back on error; the
  route must not commit itself.
- `apps/api/app/services/chat.py` — the whole module (session-first services that `flush()`,
  never `commit()`); `app/services/errors.py:36-39` (`NotFoundError`, code `not_found`).
- `apps/api/app/models/schemas/public.py` — the module the new request DTO joins.
- `apps/api/app/models/schemas/chat.py` — `ChatRequest`'s validation style.
- `apps/api/scripts/export_openapi.py`; `apps/admin/package.json` + `apps/client/package.json`
  `codegen` scripts.

## Files

**Create**
- `apps/api/tests/test_public_chat_feedback.py`

**Modify**
- `apps/api/app/models/schemas/public.py` (add `ChatFeedbackRequest`)
- `apps/api/app/services/chat.py` (add `set_message_feedback`)
- `apps/api/app/routes/public_routes.py` (add the route)

**Regenerate (same commit)**
- `apps/api/openapi.json` (`cd apps/api && uv run python scripts/export_openapi.py`)
- `apps/admin/src/types/generated/schema.d.ts` (`pnpm -C apps/admin codegen`)
- `apps/client/src/types/generated/schema.d.ts` (`pnpm -C apps/client codegen`)

## Interfaces

**Wire contract (task 17's client UI consumes this):**

| Case | Response |
|---|---|
| `{"value": 1}` or `{"value": -1}` on an existing `role='assistant'` row | `204`, empty body; `chat_messages.feedback` = that value |
| repeated call on the same message | `204`; last write wins (no conflict — a client may change its mind) |
| `message_id` unknown, soft/absent, or names a `role='user'` row | `404` `{"error": {"code": "not_found", ...}}` |
| `{"value": 0}`, `{"value": 5}`, `{}`, non-integer | `422` |
| `message_id` not a UUID | `422` (path validation) |

**`app/models/schemas/public.py`:**

```python
class ChatFeedbackRequest(BaseModel):
    """`POST /public/chat/{message_id}/feedback`'s body (phase-9 DESIGN §A, D2).

    `Literal[-1, 1]` is the whole validation: `0` ("neutral") is deliberately NOT a legal value —
    a row with no feedback stays NULL, so "never asked" and "asked, felt neutral" are never
    conflated. Anything else is a 422 before the service or the DB CHECK is ever reached.
    """

    value: Literal[-1, 1]
```

**`app/services/chat.py`:**

```python
def set_message_feedback(session: Session, message_id: uuid.UUID, value: int) -> ChatMessage:
    """Record 👍/👎 on one assistant turn (phase-9 DESIGN §A).

    Args:
        session: the caller's `Session` (CONVENTIONS.md §3 session-first; flush only).
        message_id: the `ChatMessage.id` the `done` SSE event handed the client.
        value: `-1` or `1` — already validated on the wire by `ChatFeedbackRequest`.

    Returns:
        The updated `ChatMessage` row.

    Raises:
        NotFoundError: no such row, or the row is not an assistant turn — a user message has no
            answer to rate, and the two cases are deliberately indistinguishable to the caller
            (same §9 envelope), since the client never legitimately holds a user-row id.
    """
```

Implementation: `message = session.get(ChatMessage, message_id)`; if `message is None or
message.role != "assistant"` raise `NotFoundError(f"No assistant message {message_id}.")`; else
`message.feedback = value; session.flush(); return message`.

**`app/routes/public_routes.py`:**

```python
_FEEDBACK_RESPONSES: dict[int | str, dict[str, object]] = {404: {"model": ErrorEnvelope}}


@router.post(
    "/public/chat/{message_id}/feedback",
    operation_id="public_chat_feedback",
    status_code=204,
    responses=_FEEDBACK_RESPONSES,
)
def public_chat_feedback(
    message_id: uuid.UUID,
    body: ChatFeedbackRequest,
    session: Session = Depends(get_session),
) -> Response:
    """PRD §5.3 surface, phase-9 DESIGN §A: record 👍/👎 on one assistant answer.

    Unauthenticated like every other route in this module; the `message_id` from the `done` SSE
    event is the only capability required. Not rate-limited — see the ruling below.
    """
    set_message_feedback(session, message_id, body.value)
    return Response(status_code=204)
```

New imports: `Response` from `fastapi`, `ChatFeedbackRequest` from `app.models.schemas.public`,
`set_message_feedback` added to the existing `from app.services.chat import ...` line.

**Ruling — rate limiting (decide-and-justify, per the task brief): NOT rate-limited.**
`rate_limiter.check_message` is the wrong instrument: it charges the per-minute *chat* bucket
(`RATE_LIMIT_PER_MIN=10`) and a per-day *session* bucket, so ten thumb clicks would deny the
user's own next question — a self-inflicted denial of service on the demo's most-clicked control.
The endpoint is also cheap and un-enumerable: one indexed PK lookup plus a one-column UPDATE,
addressed by a server-minted UUIDv4 the caller must already possess, writing a value constrained
to ±1 by both Pydantic and the DB CHECK, and creating no rows. The blast radius of abuse is
"someone flips their own answer's rating repeatedly", which the last-write-wins semantics already
absorb. If replay traffic (task 18) or prod logs ever show abuse, the follow-up is a *separate*
cheap per-IP counter on `RateLimiter`, never sharing the chat buckets — recorded as a
controller-visible decision, not deferred silently.

## Steps (TDD)

- [ ] **RED — test-author.** Create `apps/api/tests/test_public_chat_feedback.py`:

```python
"""`POST /public/chat/{message_id}/feedback` pins (phase-9 task-02, DESIGN §A/D2)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db import make_session_factory
from app.factory import create_app
from app.models import ChatMessage, ChatSession

_PATH = "/api/v1/public/chat/{message_id}/feedback"


def _build_client(tmp_engine: Engine) -> TestClient:
    return TestClient(create_app(session_factory=make_session_factory(tmp_engine)))


def _seed_exchange(session: Session) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert one user + one assistant row; return `(assistant_id, user_id)`."""
    chat_session = ChatSession()
    session.add(chat_session)
    session.flush()
    user = ChatMessage(session_id=chat_session.id, role="user", content="What about RSUs?")
    assistant = ChatMessage(
        session_id=chat_session.id,
        role="assistant",
        content="RSUs are taxed as ordinary income at vest.",
        citations=[],
        retrieval_found=True,
        top_similarity=0.8,
    )
    session.add_all([user, assistant])
    session.flush()
    session.commit()
    return assistant.id, user.id


def test_thumbs_up_returns_204_and_persists_plus_one(
    tmp_engine: Engine, db_session: Session
) -> None:
    assistant_id, _user_id = _seed_exchange(db_session)
    client = _build_client(tmp_engine)

    response = client.post(_PATH.format(message_id=assistant_id), json={"value": 1})

    assert response.status_code == 204
    assert response.content == b""
    with make_session_factory(tmp_engine)() as fresh:
        row = fresh.get(ChatMessage, assistant_id)
        assert row is not None and row.feedback == 1


def test_thumbs_down_then_up_keeps_the_last_value(
    tmp_engine: Engine, db_session: Session
) -> None:
    assistant_id, _user_id = _seed_exchange(db_session)
    client = _build_client(tmp_engine)

    assert client.post(_PATH.format(message_id=assistant_id), json={"value": -1}).status_code == 204
    assert client.post(_PATH.format(message_id=assistant_id), json={"value": 1}).status_code == 204

    with make_session_factory(tmp_engine)() as fresh:
        row = fresh.get(ChatMessage, assistant_id)
        assert row is not None and row.feedback == 1


def test_unknown_message_id_returns_404_envelope(tmp_engine: Engine) -> None:
    client = _build_client(tmp_engine)

    response = client.post(_PATH.format(message_id=uuid.uuid4()), json={"value": 1})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_user_role_message_id_returns_404_and_writes_nothing(
    tmp_engine: Engine, db_session: Session
) -> None:
    _assistant_id, user_id = _seed_exchange(db_session)
    client = _build_client(tmp_engine)

    response = client.post(_PATH.format(message_id=user_id), json={"value": -1})

    assert response.status_code == 404
    with make_session_factory(tmp_engine)() as fresh:
        row = fresh.get(ChatMessage, user_id)
        assert row is not None and row.feedback is None


def test_values_other_than_plus_or_minus_one_are_422(
    tmp_engine: Engine, db_session: Session
) -> None:
    assistant_id, _user_id = _seed_exchange(db_session)
    client = _build_client(tmp_engine)

    for body in ({"value": 0}, {"value": 5}, {"value": "up"}, {}):
        response = client.post(_PATH.format(message_id=assistant_id), json=body)
        assert response.status_code == 422, body

    with make_session_factory(tmp_engine)() as fresh:
        row = fresh.get(ChatMessage, assistant_id)
        assert row is not None and row.feedback is None


def test_non_uuid_message_id_is_422(tmp_engine: Engine) -> None:
    client = _build_client(tmp_engine)

    response = client.post("/api/v1/public/chat/not-a-uuid/feedback", json={"value": 1})

    assert response.status_code == 422
```

- [ ] **Run RED:** `cd apps/api && uv run pytest tests/test_public_chat_feedback.py -q` → all six
  FAIL with 404/405 (route absent). Paste the failure lines into the test-author report.

- [ ] **GREEN — implementer.** Add the DTO, the service function, and the route per Interfaces
  (`Literal` import in `public.py`; `uuid` is already imported in `public_routes.py`). Then
  regenerate the three baselines:
  `uv run python scripts/export_openapi.py && pnpm -C apps/admin codegen && pnpm -C apps/client codegen`.
  Confirm the `openapi.json` diff is confined to the new `public_chat_feedback` operation and the
  new `ChatFeedbackRequest` component schema.

- [ ] **Run GREEN:** `uv run pytest tests/test_public_chat_feedback.py -q`, then `uv run pytest -q`
  (the whole suite — `tests/test_openapi_baseline.py`-style pins, if any, must be regenerated not
  weakened).

- [ ] **Gates:** `pnpm gates:api` (incl. **lint-imports**) clean; `pnpm -C apps/admin type-check &&
  pnpm -C apps/client type-check` clean.

- [ ] **Commit:**
  `git add apps/api/app apps/api/tests/test_public_chat_feedback.py apps/api/openapi.json apps/admin/src/types/generated/schema.d.ts apps/client/src/types/generated/schema.d.ts`
  `git commit -m "feat(api): POST /public/chat/{message_id}/feedback (p9 t02)"`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=… uv run pytest tests/test_public_chat_feedback.py -q
uv run python scripts/export_openapi.py && git diff --stat -- openapi.json   # must show a diff
pnpm gates:api
```

## Acceptance

- The five wire cases in the Interfaces table hold exactly, including "a user-row id is a 404 and
  writes nothing".
- The route contains no `try/except`; `NotFoundError` reaches the §9 envelope through
  `register_error_handlers`; no `session.commit()` in the route (the dependency owns it).
- `operation_id` is exactly `public_chat_feedback`; `404` is declared on the route, not the router.
- `openapi.json` + both `schema.d.ts` regenerated in the same commit; no other operation moved.
- The rate-limiting ruling above is restated verbatim in the implementer report (it is a decision
  the reviewer must confirm, not an omission).

## Report

- Test-author: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-02-test-author.md`
- Implementer: `.superpowers/sdd/phase-9-eval-data-loop/reports/task-02-implementer.md`
