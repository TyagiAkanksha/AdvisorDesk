"""Gates-as-test: pins on the committed prod config (6R-04, WR-03).

`infra/deploy/prod/docker-compose.yml` and `infra/deploy/prod/Caddyfile` are the doc-of-record
copies of what runs on the box (see `infra/deploy/prod/README.md`). `FORWARDED_ALLOW_IPS=*`'s
safety in production rests on exactly two facts: (1) Caddy overwrites `X-Forwarded-For` with the
real client IP before the api ever sees it, and (2) the api container is never reachable except
through Caddy. This file pins both directly against the committed files so a future edit that
breaks either fact fails a test instead of only a docstring assertion.

Skips cleanly (with a reason) when the files are absent, so the suite stays runnable on checkouts
predating this task (e.g. a stale worktree from before 6R-04 landed) — never a silent omission,
per CONVENTIONS.md's skip-by-name discipline (see `conftest.py`, `test_ci_guard.py`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROD_DIR = _REPO_ROOT / "infra" / "deploy" / "prod"
_COMPOSE_PATH = _PROD_DIR / "docker-compose.yml"
_CADDYFILE_PATH = _PROD_DIR / "Caddyfile"


def _skip_if_absent() -> None:
    """Skip with a reason if either pinned file is missing (pre-6R-04 checkout)."""
    missing = [p for p in (_COMPOSE_PATH, _CADDYFILE_PATH) if not p.is_file()]
    if missing:
        names = ", ".join(str(p.relative_to(_REPO_ROOT)) for p in missing)
        pytest.skip(f"infra/deploy/prod files not present on this checkout: {names}")


def _strip_caddyfile_comments(text: str) -> str:
    """Strip Caddyfile `#`-to-end-of-line comments from every line.

    Caddy treats `#` as a comment marker to end-of-line, so a commented-out directive is
    inert in the real proxy. Stripping comments before matching keeps a disabled
    `header_up` line (fix round 1, review Important finding) from satisfying a check that
    is meant to pin an *active* directive.
    """
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def test_caddyfile_overwrites_forwarded_for_on_api_block() -> None:
    """The api host block must overwrite (not append) X-Forwarded-For with {remote_host}.

    This is the spoof-proofing half of WR-03: Caddy faces the internet directly, so
    `{remote_host}` is the true end-user IP, and overwriting discards any client-forged
    X-Forwarded-For before the api's rate limiter ever keys on it. The match is
    comment-aware and line-anchored (not a raw substring test) so a `header_up` line that
    has been commented out — disabled in real Caddy — fails this check rather than
    passing it.
    """
    _skip_if_absent()
    text = _CADDYFILE_PATH.read_text()
    match = re.search(r"^api\.\S+\s*\{(.*?)^\}", text, re.DOTALL | re.MULTILINE)
    assert match, "no api.<host> block found in the committed Caddyfile"
    api_block = _strip_caddyfile_comments(match.group(1))
    directive = re.search(r"(?m)^\s*header_up\s+X-Forwarded-For\s+\{remote_host\}\s*$", api_block)
    assert directive, (
        "api host block must have an active (uncommented) "
        "'header_up X-Forwarded-For {remote_host}' line"
    )


def test_compose_does_not_publish_api_port_to_host() -> None:
    """The api service must stay unreachable except through Caddy (the other WR-03 half).

    `expose` makes the port reachable to other containers on the compose network only;
    a `ports:` mapping would additionally publish it to the host (and, on this box, to the
    internet), which would let a caller bypass Caddy's X-Forwarded-For overwrite entirely.
    """
    _skip_if_absent()
    compose = yaml.safe_load(_COMPOSE_PATH.read_text())
    api_service = compose["services"]["api"]
    assert "ports" not in api_service, "api service must not publish ports to the host"
    assert api_service.get("expose"), "api service must expose (not publish) its port"
