"""Unit tests for the six new OAuth `Settings` fields, the `mcp_resource_url` property, and the
`oauth_issuer_url` validator (docs/plans/mcp-oauth/task-01-data-model-migration.md; DESIGN.md
§"Token & data model").

`Settings()` must stay zero-env-var constructible (CONVENTIONS.md §5) — the six new fields all
ship with defaults. `oauth_issuer_url`'s validator strips exactly one trailing slash and rejects
a value that isn't a full `http://`/`https://` URL; `mcp_resource_url` derives the canonical MCP
resource URI from it (`f"{oauth_issuer_url}/api/v1/mcp"`).

Neither test touches a database. RED today: none of `oauth_issuer_url`,
`oauth_access_token_ttl_minutes`, `oauth_refresh_token_ttl_days`, `oauth_auth_code_ttl_seconds`,
`oauth_rate_limit_per_min`, `oauth_max_clients`, or `mcp_resource_url` exist on `Settings` yet —
`test_defaults_are_zero_env` fails with `AttributeError` on the first missing field;
`test_issuer_trailing_slash_stripped`/`test_issuer_must_be_http_url` both fail because
`Settings(oauth_issuer_url=...)` currently raises `pydantic.ValidationError` for the WRONG
reason (`extra_forbidden` — pydantic-settings rejects an unrecognized kwarg outright, since the
field doesn't exist yet), never reaching the trailing-slash/http-prefix behavior these tests
actually pin.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_defaults_are_zero_env() -> None:
    """`Settings()` with zero env vars set carries the six new OAuth defaults plus the derived
    `mcp_resource_url` property (task-01 brief Interfaces block, verbatim defaults)."""
    settings = Settings()

    assert settings.oauth_issuer_url == "http://localhost:8000"
    assert settings.oauth_access_token_ttl_minutes == 60
    assert settings.oauth_refresh_token_ttl_days == 30
    assert settings.oauth_auth_code_ttl_seconds == 60
    assert settings.oauth_rate_limit_per_min == 30
    assert settings.oauth_max_clients == 200
    assert settings.mcp_resource_url == "http://localhost:8000/api/v1/mcp"


def test_issuer_trailing_slash_stripped() -> None:
    """The `oauth_issuer_url` validator strips exactly one trailing slash, so a copy-pasted
    issuer URL with a trailing `/` still composes correctly with `mcp_resource_url`'s own
    `f"{oauth_issuer_url}/api/v1/mcp"` (no accidental `//api/v1/mcp`)."""
    settings = Settings(oauth_issuer_url="https://x.example/")

    assert settings.oauth_issuer_url == "https://x.example"


def test_issuer_whitespace_stripped() -> None:
    """The `oauth_issuer_url` validator strips leading/trailing whitespace before validating the
    scheme and stripping the trailing slash — a hand-edited `.env` value with a stray space (fix
    round 1, M2) must not produce a rejected or malformed issuer URL."""
    settings = Settings(oauth_issuer_url=" https://x.example/ ")

    assert settings.oauth_issuer_url == "https://x.example"


def test_issuer_must_be_http_url() -> None:
    """The validator rejects a value that isn't a full `http://`/`https://` URL — and does so as
    a genuine value-level validation failure, not merely because the field doesn't exist yet.

    Discriminates real RED from a false pass (mirrors `tests/test_llm_provider_config.py::
    test_llm_provider_rejects_an_unrecognized_value`'s own technique): at current HEAD,
    `Settings(oauth_issuer_url="x.example")` ALREADY raises `ValidationError`, but as
    `errors()[0]["type"] == "extra_forbidden"` (the field is unrecognized), not because "x.example"
    was checked and rejected for missing an http(s) scheme. A `pydantic.field_validator`/
    `model_validator` that raises `ValueError` on a bad value produces `errors()[0]["type"] ==
    "value_error"` — asserting that type is what makes this test fail now and pass only once the
    real issuer check exists.
    """
    with pytest.raises(ValidationError) as exc_info:
        Settings(oauth_issuer_url="x.example")

    assert exc_info.value.errors()[0]["type"] == "value_error"


def test_issuer_rejects_embedded_whitespace() -> None:
    """Fix round 1, review finding M-3 (Minor, defence-in-depth): the validator rejects any
    whitespace/control character REMAINING after `.strip()` trims the two ends — `.strip()` alone
    would let an embedded `\\r\\n` (e.g. an operator accidentally pasting a raw HTTP header line
    into `OAUTH_ISSUER_URL`) survive validation and later be emitted verbatim into the RFC 9728
    `WWW-Authenticate` response header. Mirrors `test_issuer_must_be_http_url`'s own
    `errors()[0]["type"] == "value_error"` technique to confirm this is a genuine value-level
    rejection, not an incidental failure for some other reason."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(oauth_issuer_url="https://x.example\r\nX: y")

    assert exc_info.value.errors()[0]["type"] == "value_error"
