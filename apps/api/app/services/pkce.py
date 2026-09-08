"""RFC 7636 PKCE helpers (mcp-oauth plan, task 05).

Pure leaf module — stdlib only (`re`, `base64`, `hashlib`, `hmac`) — mirroring
`app.services.token_hashing`'s own "pure even within the already-restricted `app.services`
package" shape (import-linter contract: `app.services` imports only `app.models`/`app.config`;
this module imports neither, so it trivially satisfies that).

RFC 7636 §4.1/§4.2: both `code_verifier` and `code_challenge` are 43-128 characters drawn from
the "unreserved" charset `[A-Za-z0-9._~-]` — exactly base64url-without-padding's own alphabet
(RFC 7636 §4.2's own recommended `code_challenge` construction), which is why one regex validates
both. `verify_s256` implements the S256 transform (RFC 7636 §4.2):
`base64url(SHA256(ascii(verifier)))` with the trailing `=` padding stripped, compared to
`code_challenge` with `hmac.compare_digest` —
a constant-time comparison, since a challenge (once minted by a real client) is not itself secret,
but there is no reason to prefer a short-circuiting `==` over a comparison that already exists and
is exactly this reviewer- and RFC-scrutinized code path's business to get right.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re

_UNRESERVED = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")


def is_valid_code_challenge(value: str) -> bool:
    """Whether `value` is a well-formed RFC 7636 §4.2 `code_challenge`: 43-128 chars of
    `[A-Za-z0-9._~-]`."""
    return bool(_UNRESERVED.fullmatch(value))


def is_valid_code_verifier(value: str) -> bool:
    """Whether `value` is a well-formed RFC 7636 §4.1 `code_verifier` — the identical
    43-128/`[A-Za-z0-9._~-]` rule as `is_valid_code_challenge`."""
    return bool(_UNRESERVED.fullmatch(value))


def verify_s256(code_verifier: str, code_challenge: str) -> bool:
    """Whether `code_verifier` hashes (RFC 7636 §4.6 S256 transform) to `code_challenge`.

    `code_verifier` is ASCII-encoded before hashing (RFC 7636 §4.1: the verifier itself is
    restricted to the unreserved charset, a strict subset of ASCII, so this never raises).

    Args:
        code_verifier: the `code_verifier` presented at the token endpoint.
        code_challenge: the `code_challenge` recorded at authorize time.

    Returns:
        `True` iff `base64url(sha256(code_verifier))` (padding stripped) equals `code_challenge`,
        compared in constant time.
    """
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return hmac.compare_digest(expected, code_challenge)
