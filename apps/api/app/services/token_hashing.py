"""Shared token hash/generate leaf (mcp-oauth plan, task-01; docs/plans/mcp-oauth/DESIGN.md
§"Token & data model").

Every secret this codebase mints (the existing `"adk_"` MCP bearer token, and the new OAuth
authorization codes / refresh tokens) follows the same shape: a CSPRNG-backed random raw value,
prefixed so its kind is identifiable at a glance, with only its sha256 hex digest ever persisted.
`app.auth.tokens.mint_token` used to inline this pair itself; it now delegates here so the OAuth
tables (`app.models.oauth`) can hash their own secrets identically without duplicating the logic.

Import-linter contract (`apps/api/pyproject.toml`, "app.services imports only app.models and
app.config"): this module additionally may import ONLY the standard library — no `app.models`, no
`app.config`, nothing — it is a pure leaf even within the already-restricted `app.services`
package.
"""

from __future__ import annotations

import hashlib
import secrets


def hash_token(raw: str) -> str:
    """Return the sha256 hex digest of `raw` — the only form of a secret ever persisted.

    Args:
        raw: the full raw secret value (e.g. `"adk_" + secrets.token_urlsafe(32)`).

    Returns:
        A 64-character lowercase hex digest.
    """
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_token(prefix: str) -> tuple[str, str]:
    """Generate one new CSPRNG-backed secret: `(raw, hash_token(raw))`.

    `raw` is exactly `prefix + secrets.token_urlsafe(32)` — `secrets.token_urlsafe` is the same
    CSPRNG session cookies and the pre-existing `"adk_"` bearer tokens already rely on.

    Args:
        prefix: identifies the secret's kind at a glance (e.g. `"adk_"`, `"adkr_"`).

    Returns:
        `(raw, hashed)` — `raw` is the caller's one-time value to hand back to its owner;
        `hashed` is the only form the caller should ever persist.
    """
    raw = f"{prefix}{secrets.token_urlsafe(32)}"
    return raw, hash_token(raw)
