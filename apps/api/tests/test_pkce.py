"""Failing (RED) tests for RFC 7636 PKCE helpers (mcp-oauth plan, task 05).

Task brief: docs/plans/mcp-oauth/task-05-authorize-pkce-google-bridge.md. Spec: RFC 7636
(`code_verifier`/`code_challenge` charset+length, S256 transform).

Today `app.services.pkce` does not exist at all, so every test below fails at COLLECTION
(`ModuleNotFoundError`) — an acceptable whole-file RED per the test-author brief's own
constraints block ("collection ModuleNotFoundError counts as RED for whole files"). No DB is
needed anywhere in this file: `is_valid_code_challenge`/`is_valid_code_verifier`/`verify_s256`
are pure, stdlib-only functions (the module's own Interfaces-block docstring: "pure leaf (stdlib
only)").

The RFC 7636 vector below (`_VERIFIER` <-> `_CHALLENGE`) is Appendix B's own worked example:
`S256(_VERIFIER) == _CHALLENGE`.
"""

from __future__ import annotations

from app.services.pkce import is_valid_code_challenge, is_valid_code_verifier, verify_s256

_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_rfc7636_appendix_b_vector() -> None:
    """RFC 7636 Appendix B's worked example: `S256(_VERIFIER) == _CHALLENGE`."""
    assert verify_s256(_VERIFIER, _CHALLENGE) is True


def test_wrong_verifier_false() -> None:
    """A verifier that does NOT hash to `_CHALLENGE` must fail — `verify_s256` is not a tautology
    that returns `True` for any well-formed input."""
    assert verify_s256("a" * 43, _CHALLENGE) is False


def test_challenge_charset_and_length() -> None:
    """RFC 7636 §4.2: `code_challenge` is 43-128 chars of `[A-Za-z0-9._~-]` (unreserved,
    base64url-without-padding's alphabet). 42 chars is one short of the minimum; 129 is one over
    the maximum; a `+` is outside the allowed charset even at a valid length."""
    assert is_valid_code_challenge("a" * 42) is False
    assert is_valid_code_challenge("a" * 43) is True
    assert is_valid_code_challenge("a" * 128) is True
    assert is_valid_code_challenge("a" * 129) is False
    assert is_valid_code_challenge("a" * 42 + "+") is False


def test_verifier_charset_and_length() -> None:
    """RFC 7636 §4.1: `code_verifier` has the identical 43-128/`[A-Za-z0-9._~-]` rule as
    `code_challenge` — the same boundary cases apply."""
    assert is_valid_code_verifier("a" * 42) is False
    assert is_valid_code_verifier("a" * 43) is True
    assert is_valid_code_verifier("a" * 128) is True
    assert is_valid_code_verifier("a" * 129) is False
    assert is_valid_code_verifier("a" * 42 + "+") is False
