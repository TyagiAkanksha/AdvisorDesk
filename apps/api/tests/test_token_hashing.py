"""Unit tests for `app.services.token_hashing` — the shared token-hash/generate leaf the
mcp-oauth plan introduces (docs/plans/mcp-oauth/task-01-data-model-migration.md; DESIGN.md
§"Token & data model").

`app.auth.tokens.mint_token` currently inlines its own `secrets.token_urlsafe(32)` +
`hashlib.sha256(...).hexdigest()` pair. Task 01 pulls that into a provider-neutral leaf
(`app/services/token_hashing.py`: `generate_token(prefix) -> (raw, hash)`, `hash_token(raw) ->
hash`) so the new OAuth authorization-code/refresh-token rows (task-01 brief's four new tables)
can hash their own secrets the same way, and `mint_token()` is refactored to delegate to it with
its return shape UNCHANGED (still `"adk_" + secrets.token_urlsafe(32)` and its sha256 hex).

Neither test touches a database — pure functions only. RED today: `app.services.token_hashing`
does not exist at all, so the module-level import below fails at collection with `ImportError`,
taking down every test in this file (task-01 test-author instructions: a whole-module
collection-time ImportError is acceptable RED — the natural shape for a not-yet-existing leaf,
no need to contort the import to be deferred per-test).
"""

from __future__ import annotations

import hashlib

from app.auth.tokens import mint_token
from app.services.token_hashing import generate_token, hash_token


def test_generate_token_prefix_and_hash_roundtrip() -> None:
    """`generate_token(prefix)` returns `(raw, hashed)` where `raw` starts with `prefix`,
    `hashed` is exactly `hash_token(raw)`, and `hashed` is a 64-hex-char sha256 digest — the
    same shape `mint_token()` pins for the existing `"adk_"` bearer tokens (task-01 brief:
    `generate_token(prefix) -> (prefix + secrets.token_urlsafe(32), hash_token(raw))`)."""
    raw, hashed = generate_token("adkr_")

    assert raw.startswith("adkr_")
    assert hash_token(raw) == hashed
    assert len(hashed) == 64


def test_mint_token_unchanged_shape() -> None:
    """`app.auth.tokens.mint_token()` keeps its pre-task-01 return shape after delegating to
    `generate_token("adk_")` — an `"adk_"`-prefixed raw token and its sha256 hex hash (task-01
    brief: "behavior and return shape unchanged; `_TOKEN_PREFIX` stays exported")."""
    raw, hashed = mint_token()

    assert raw.startswith("adk_")
    assert hashed == hashlib.sha256(raw.encode()).hexdigest()
