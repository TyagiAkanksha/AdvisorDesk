"""Dump the OpenAPI schema from a DB-less `create_app()` to `openapi.json` (CONVENTIONS.md §8).

Deterministic output (`sort_keys=True`, indent 2, trailing newline) so
`git diff --exit-code openapi.json` proves the wire surface did not move —
the frontends' `openapi-typescript` codegen (task-04) depends on this
baseline never drifting silently. Any commit that changes a route or DTO
must regenerate this file in the same commit (CONVENTIONS.md §8).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.factory import create_app

_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "openapi.json"


def main() -> None:
    """Build `create_app()` with no args and write its OpenAPI schema deterministically."""
    app = create_app()
    payload = app.openapi()
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    _OUTPUT_PATH.write_text(text)


if __name__ == "__main__":
    main()
