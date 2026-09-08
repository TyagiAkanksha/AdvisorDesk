"""t01 carry-over: `OAuthRefreshToken.access_token_id`/`rotated_from_id` `ondelete="SET NULL"`
FKs, pinned by task 07's dispatch since they went untested through tasks 01-06.

Task brief: docs/plans/mcp-oauth/task-07-token-refresh-rotation.md (this module is not itself
named by that brief's own test list — it is a controller-added carry-over covering a t01,
migration-0007 behavior that task 07's `oauth_tokens.py` is the first thing to actually rely on:
`rotate_refresh_token` deletes an old `ApiToken` row via `client_id`/`access_token_id`, and this is
the empirical proof that deleting the referenced row does NOT cascade-delete or orphan the
`oauth_refresh_tokens` row pointing at it — it survives with the FK column nulled instead).

`app/models/oauth.py`'s own docstring pins the design: "A refresh token's own optional
back-references (`access_token_id` ... `rotated_from_id` ...) are `SET NULL` instead [of CASCADE]
— the refresh token row itself stays a historical/audit record even after the thing it points to
is gone." Both constraints were created by migration 0007 (task 01), well before this task — pure
ORM/DB tests, no HTTP surface, no dependency on the not-yet-existing `/token` route or
`app.services.oauth_tokens` module.

Both tests below are expected to ALREADY PASS today: they exercise a migration that landed in
task 01, not any of this task's new code. Kept as regression guards (not previously covered by any
existing test file — grepped `tests/test_oauth_*.py`/`tests/test_migrations*.py` for
`access_token_id`/`rotated_from_id`, no hits) rather than dropped, so a future migration change
that accidentally weakens either constraint (e.g. a CASCADE regression) is caught here.

CONVENTIONS.md §10: both tests request `db_session` (skipped by fixture name when
`TEST_DATABASE_URL` is unset).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import User
from app.models.api_tokens import ApiToken
from app.models.oauth import OAuthClient, OAuthRefreshToken
from app.services.token_hashing import hash_token

_RESOURCE = "https://api.example/api/v1/mcp"


def test_deleting_access_token_row_sets_refresh_row_access_token_id_null(
    db_session: Session,
) -> None:
    """Deleting the `ApiToken` row an `OAuthRefreshToken.access_token_id` points at nulls that
    column on the refresh row rather than deleting (or orphaning) the refresh row itself."""
    client = OAuthClient(
        client_id="adkc_fk-access-token-test",
        client_name="FK Access Token Test Client",
        redirect_uris=["https://example.com/callback"],
    )
    owner = User(email="fk-access-token-test@example.com", name="FK Access Token Test User")
    db_session.add_all([client, owner])
    db_session.flush()

    access = ApiToken(
        user_id=owner.id,
        token_hash=hash_token("adk_fk-access-token-test"),
        name="oauth:fk-access-token-test",
        session_epoch=owner.session_epoch,
        client_id=client.client_id,
        resource=_RESOURCE,
    )
    db_session.add(access)
    db_session.flush()

    refresh = OAuthRefreshToken(
        token_hash=hash_token("adkr_fk-access-token-test"),
        client_id=client.client_id,
        user_id=owner.id,
        access_token_id=access.id,
        family_id=uuid.uuid4(),
        resource=_RESOURCE,
        scope="mcp",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(refresh)
    db_session.flush()
    refresh_id = refresh.id

    db_session.delete(access)
    db_session.commit()
    db_session.expire_all()

    surviving_row = db_session.get(OAuthRefreshToken, refresh_id)
    assert surviving_row is not None
    assert surviving_row.access_token_id is None


def test_deleting_rotated_from_refresh_row_sets_rotated_from_id_null(db_session: Session) -> None:
    """Deleting the PREDECESSOR `OAuthRefreshToken` row a later row's `rotated_from_id` points at
    nulls that column on the later row rather than deleting (or orphaning) it — the later row stays
    a valid, live refresh token/audit record even after its rotation predecessor is gone."""
    client = OAuthClient(
        client_id="adkc_fk-rotated-from-test",
        client_name="FK Rotated From Test Client",
        redirect_uris=["https://example.com/callback"],
    )
    owner = User(email="fk-rotated-from-test@example.com", name="FK Rotated From Test User")
    db_session.add_all([client, owner])
    db_session.flush()

    family_id = uuid.uuid4()
    first = OAuthRefreshToken(
        token_hash=hash_token("adkr_fk-rotated-from-test-first"),
        client_id=client.client_id,
        user_id=owner.id,
        family_id=family_id,
        resource=_RESOURCE,
        scope="mcp",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(first)
    db_session.flush()

    second = OAuthRefreshToken(
        token_hash=hash_token("adkr_fk-rotated-from-test-second"),
        client_id=client.client_id,
        user_id=owner.id,
        family_id=family_id,
        rotated_from_id=first.id,
        resource=_RESOURCE,
        scope="mcp",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(second)
    db_session.flush()
    second_id = second.id

    db_session.delete(first)
    db_session.commit()
    db_session.expire_all()

    surviving_row = db_session.get(OAuthRefreshToken, second_id)
    assert surviving_row is not None
    assert surviving_row.rotated_from_id is None
