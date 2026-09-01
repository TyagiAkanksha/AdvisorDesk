"""Gates-as-test: pins on the committed prod Caddyfile's security response headers (6R-05, WR-04).

Design-pin rationale (CORRECTED — the cross-site-iframe clickjacking scenario was refuted by the
verifier: Lax-cookies aren't sent on cross-site iframe loads, so that framing threat doesn't hold).
The real drivers pinned here are (1) the first-visit HTTP->HTTPS downgrade window before a client
has ever seen an HSTS response, and (2) same-registrable-domain framing (nothing on
`*.advisordesk.tyagiakanksha.com` should be able to frame another host on the same registrable
domain, and nothing legitimate frames the JSON API either).

`infra/deploy/prod/Caddyfile` is the doc-of-record copy of what runs on the box (see
`infra/deploy/prod/README.md`); this task adds the same five-header set at the edge to all three
site blocks (api, admin, client) — the three headers Next.js can't apply for the API origin, plus
frame defense that covers all three hosts equally per the corrected rationale above.

Kept as a SEPARATE file from `test_prod_config_pins.py` (6R-04's pinned file) precisely so that
file stays byte-stable — this file pins only the new header directives.

Skips cleanly (with a reason) when the Caddyfile is absent, so the suite stays runnable on
checkouts predating 6R-04/6R-05, per CONVENTIONS.md's skip-by-name discipline (see `conftest.py`,
`test_ci_guard.py`). Requires no database.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CADDYFILE_PATH = _REPO_ROOT / "infra" / "deploy" / "prod" / "Caddyfile"

# The full pinned header set (WR-04 design pins): the three edge headers common to all three
# hosts, plus the two frame-defense headers, which the brief's corrected rationale says apply to
# *all three* blocks — including the API host ("the API host gets the frame headers too — nothing
# legitimate frames JSON"), not only the two app hosts.
_PINNED_HEADERS: tuple[tuple[str, str], ...] = (
    ("Strict-Transport-Security", "max-age=31536000; includeSubDomains"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("X-Frame-Options", "DENY"),
    ("Content-Security-Policy", "frame-ancestors 'none'"),
)


def _skip_if_absent() -> None:
    """Skip with a reason if the Caddyfile is missing (pre-6R-04 checkout)."""
    if not _CADDYFILE_PATH.is_file():
        pytest.skip(
            f"infra/deploy/prod/Caddyfile not present on this checkout: "
            f"{_CADDYFILE_PATH.relative_to(_REPO_ROOT)}"
        )


def _strip_caddyfile_comments(text: str) -> str:
    """Strip Caddyfile `#`-to-end-of-line comments from every line.

    Caddy treats `#` as a comment marker to end-of-line, so a commented-out directive is inert
    in the real proxy. Stripping comments before matching keeps a disabled header line from
    satisfying a check that is meant to pin an *active* directive (mirrors
    `test_prod_config_pins.py`'s helper, reimplemented locally per this file's brief so that
    file's byte-stability isn't disturbed by a cross-file import).
    """
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _extract_site_block(text: str, host_line_prefix: str) -> str:
    """Return the comment-stripped body of the site block whose host starts with the prefix.

    Line-anchored on the host (not a raw substring search) and terminated at the first
    column-0 `}` — this holds even once the implementer nests a `header { ... }` sub-block
    inside the site block, because Caddyfile indentation always keeps a nested block's closing
    brace indented, matching the existing convention in `test_prod_config_pins.py`.
    """
    pattern = rf"^{re.escape(host_line_prefix)}\S*\s*\{{(.*?)^\}}"
    match = re.search(pattern, text, re.DOTALL | re.MULTILINE)
    assert match, f"no site block starting with {host_line_prefix!r} found in the Caddyfile"
    return _strip_caddyfile_comments(match.group(1))


def _assert_header_directive(block: str, name: str, value: str) -> None:
    """Assert an active header directive for `name: value` exists in `block`.

    Tolerant of either Caddyfile spelling of the directive — the standalone form
    (`header <Name> "<value>"`) or a line inside a `header { ... }` block (`<Name> "<value>"`)
    — and of the value being quoted or not, since the brief pins header *content*, not the
    implementer's choice of directive syntax.
    """
    pattern = re.compile(
        rf'(?m)^[ \t]*(?:header\s+)?{re.escape(name)}\s+"?{re.escape(value)}"?[ \t]*$'
    )
    assert pattern.search(block), (
        f"expected an active header directive '{name}: {value}' "
        f'(as `header {name} "{value}"` or inside a `header {{ }}` block)'
    )


def test_caddyfile_api_block_has_pinned_security_headers() -> None:
    """The api.<host> block must carry all five pinned security headers.

    HSTS/nosniff/referrer-policy cover the API origin (Next.js can't set edge headers for a
    host it doesn't front); the frame-defense pair is included too per the corrected
    rationale — nothing legitimate frames a JSON API, so there's no cost to denying it.
    """
    _skip_if_absent()
    text = _CADDYFILE_PATH.read_text()
    block = _extract_site_block(text, "api.")
    for name, value in _PINNED_HEADERS:
        _assert_header_directive(block, name, value)


def test_caddyfile_admin_block_has_pinned_security_headers() -> None:
    """The admin.<host> app block must carry all five pinned security headers.

    The frame-defense pair (X-Frame-Options: DENY / CSP frame-ancestors 'none') defends
    against same-registrable-domain framing — a sibling host under
    `*.advisordesk.tyagiakanksha.com` embedding the admin app in a hidden iframe.
    """
    _skip_if_absent()
    text = _CADDYFILE_PATH.read_text()
    block = _extract_site_block(text, "admin.")
    for name, value in _PINNED_HEADERS:
        _assert_header_directive(block, name, value)


def test_caddyfile_client_block_has_pinned_security_headers() -> None:
    """The bare-domain client block must carry all five pinned security headers.

    Same same-registrable-domain framing defense as the admin block, plus the first-visit
    HTTP->HTTPS downgrade window that HSTS closes for a client that has never yet received it.
    """
    _skip_if_absent()
    text = _CADDYFILE_PATH.read_text()
    block = _extract_site_block(text, "advisordesk.")
    for name, value in _PINNED_HEADERS:
        _assert_header_directive(block, name, value)
