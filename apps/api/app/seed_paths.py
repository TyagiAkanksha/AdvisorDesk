"""Resolve the on-disk seed-data directory for both host dev and the container image.

The seed corpus (`sample_content/*.md` + `eval_questions.yaml`) lives at the repo-root `seed/`
directory in the source tree, but inside the API image it is `COPY`ed to `/app/seed` (see
`infra/Dockerfile.api`), a location no `Path(__file__).parents[...]` walk can reach from
`/app/app/seed_paths.py`. This leaf module hides that split behind one function so `app.seed` and
`app.eval.groundedness` never do path math at module scope (which crashed on import in the
container — the `parents[3]`/`parents[4]` walks went out of range under `/app/app/...`).

Deliberately a dependency-free leaf: it imports only the stdlib, never `app.seed`/`app.eval`, so
it stays importable from both without an import cycle and stays clean under the import-linter
contracts.
"""

from __future__ import annotations

import os
from pathlib import Path


def seed_data_dir() -> Path:
    """Directory holding `sample_content/` and `eval_questions.yaml`.

    Prefers the `$SEED_DATA_DIR` env var (set to `/app/seed` in the container image, so the
    container never evaluates the host fallback below). With that var unset — host dev — it falls
    back to the repo-root `seed/` directory, resolved relative to this file:
    `<repo>/apps/api/app/seed_paths.py` → `parents[3]` is the repo root
    (`parents[0]=app`, `[1]=api`, `[2]=apps`, `[3]=repo`), matching the file depth of `app/seed.py`.

    Returns:
        The seed-data directory as a `Path`. Existence is NOT checked here — callers append
        `sample_content`/`eval_questions.yaml` and read from there.
    """
    override = os.environ.get("SEED_DATA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "seed"
