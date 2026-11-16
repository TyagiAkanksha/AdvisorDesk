"""Gates-as-test: pins on the local-embedding image, prod compose and docs (Task B).

Pins `infra/Dockerfile.api`, `infra/deploy/prod/docker-compose.yml`, `.env.example`,
`advisordesk-prd.md` and the deploy docs for `EMBEDDING_PROVIDER=local` (2026-11-16).
Skips cleanly when a pinned file is absent, like `test_prod_config_pins.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DOCKERFILE = _REPO_ROOT / "infra" / "Dockerfile.api"
_COMPOSE_PATH = _REPO_ROOT / "infra" / "deploy" / "prod" / "docker-compose.yml"
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"
_PRD = _REPO_ROOT / "advisordesk-prd.md"
_PROD_README = _REPO_ROOT / "infra" / "deploy" / "prod" / "README.md"
_ENV_CHECKLIST = _REPO_ROOT / "infra" / "deploy" / "env-checklist.md"

_CACHE_DIR = "/app/.fastembed-cache"


def _read(path: Path) -> str:
    if not path.is_file():
        pytest.skip(f"{path.relative_to(_REPO_ROOT)} not present on this checkout")
    return path.read_text()


def _dockerfile_instructions() -> list[str]:
    """Dockerfile instructions with comments dropped and `\\` continuations joined."""
    text = _read(_DOCKERFILE)
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    joined = re.sub(r"\\\s*\n", " ", "\n".join(lines))
    return [ln.strip() for ln in joined.splitlines() if ln.strip()]


def _index_of(instructions: list[str], pattern: str) -> int:
    for i, line in enumerate(instructions):
        if re.search(pattern, line):
            return i
    raise AssertionError(f"no Dockerfile instruction matches /{pattern}/")


def _bake_run_index(instructions: list[str]) -> int:
    return _index_of(instructions, r"^RUN\b.*TextEmbedding")


def _api_env() -> dict[str, str]:
    compose = yaml.safe_load(_read(_COMPOSE_PATH))
    return compose["services"]["api"]["environment"]


# ---------- B1: Dockerfile ----------


def test_dockerfile_copies_scripts_into_both_stages() -> None:
    ins = _dockerfile_instructions()
    build = [i for i in ins if re.match(r"COPY\b(?!.*--from)", i) and "apps/api/scripts" in i]
    assert build, "builder stage must COPY apps/api/scripts"
    assert any(
        re.search(r"/app/scripts\b", i) and "--from=builder" in i
        for i in ins
        if i.startswith("COPY")
    ), "runtime stage must COPY --from=builder /app/scripts"


def test_dockerfile_runtime_scripts_owned_by_appuser() -> None:
    ins = _dockerfile_instructions()
    runtime = [
        i
        for i in ins
        if i.startswith("COPY") and "--from=builder" in i and re.search(r"/app/scripts\b", i)
    ]
    assert runtime, "no runtime COPY of /app/scripts"
    assert all("--chown=appuser:appuser" in i for i in runtime)
    assert any(
        re.search(r"/app/scripts\s+\./?scripts|/app/scripts\s+/app/scripts", i) for i in runtime
    )


def test_dockerfile_sets_cache_dir_env() -> None:
    ins = _dockerfile_instructions()
    assert any(re.fullmatch(rf"ENV LOCAL_EMBEDDING_CACHE_DIR[= ]{_CACHE_DIR}", i) for i in ins)


def test_dockerfile_bakes_model_before_user_switch() -> None:
    ins = _dockerfile_instructions()
    bake = _bake_run_index(ins)
    line = ins[bake]
    assert "fastembed" in line and "cache_dir" in line
    assert _CACHE_DIR in line or "$LOCAL_EMBEDDING_CACHE_DIR" in line
    assert re.search(
        r"chown -R appuser:appuser\s+\S*(\.fastembed-cache|LOCAL_EMBEDDING_CACHE_DIR)", line
    )
    assert bake < _index_of(ins, r"^USER appuser$"), (
        "bake RUN must run as root, before USER appuser"
    )
    cache_env = _index_of(ins, r"^ENV LOCAL_EMBEDDING_CACHE_DIR")
    assert cache_env < bake, "cache dir ENV must be set before the bake RUN"


def test_dockerfile_goes_offline_after_the_bake() -> None:
    ins = _dockerfile_instructions()
    offline = _index_of(ins, r"^ENV LOCAL_EMBEDDING_OFFLINE[= ]true$")
    assert offline > _bake_run_index(ins), "offline must be set AFTER the model is baked"


def test_dockerfile_healthcheck_start_period_is_40s() -> None:
    ins = _dockerfile_instructions()
    hc = ins[_index_of(ins, r"^HEALTHCHECK\b")]
    assert "--start-period=40s" in hc


def test_dockerfile_model_matches_settings_default() -> None:
    from app.config import Settings

    default = Settings.model_fields["local_embedding_model"].default
    ins = _dockerfile_instructions()
    bake = ins[_bake_run_index(ins)]
    assert default in bake, f"Dockerfile bake RUN must name {default!r}"


# ---------- B2: prod compose ----------


def test_compose_embedding_provider_is_local() -> None:
    assert _api_env()["EMBEDDING_PROVIDER"] == "local"


def test_compose_similarity_threshold_is_065() -> None:
    assert str(_api_env()["SIMILARITY_THRESHOLD"]) == "0.65"


def test_compose_embedding_dimensions_stay_1024() -> None:
    assert str(_api_env()["EMBEDDING_DIMENSIONS"]) == "1024"


def test_compose_keeps_anthropic_llm_and_leaves_embedding_model_unpinned() -> None:
    env = _api_env()
    assert env["LLM_PROVIDER"] == "anthropic"
    assert "EMBEDDING_MODEL" not in env


def test_compose_comment_no_longer_says_embeddings_stay_on_openai() -> None:
    assert "Embeddings stay on OpenAI" not in _read(_COMPOSE_PATH)


def test_compose_comment_describes_the_rollback() -> None:
    assert "scripts/reembed.py" in _read(_COMPOSE_PATH)


# ---------- B3: docs ----------


def test_env_example_documents_local_embeddings() -> None:
    text = _read(_ENV_EXAMPLE)
    assert "EMBEDDING_PROVIDER=local" in text
    for key in (
        "LOCAL_EMBEDDING_MODEL",
        "LOCAL_EMBEDDING_QUERY_PREFIX",
        "LOCAL_EMBEDDING_CACHE_DIR",
        "LOCAL_EMBEDDING_OFFLINE",
        "LOCAL_EMBEDDING_THREADS",
    ):
        assert key in text, f"{key} missing from .env.example"


def test_prd_changelog_has_v1_8_entry() -> None:
    text = _read(_PRD)
    match = re.search(r"\*\*v1\.8\*\*(.*?)(?=\n- \*\*v1\.7\*\*|\Z)", text, re.DOTALL)
    assert match, "PRD changelog needs a **v1.8** entry"
    entry = match.group(1).lower()
    assert "anthropic" in entry
    assert "embedding_provider=local" in entry


def test_prd_section_7_2_mentions_the_local_model() -> None:
    assert "bge-small-en-v1.5" in _read(_PRD)


def test_deploy_docs_mention_embedding_provider() -> None:
    existing = [p for p in (_PROD_README, _ENV_CHECKLIST) if p.is_file()]
    if not existing:
        pytest.skip("neither prod README nor env-checklist present")
    for path in existing:
        assert re.search(r"EMBEDDING_PROVIDER\W{0,6}local", path.read_text()), (
            f"{path.relative_to(_REPO_ROOT)} must document EMBEDDING_PROVIDER=local"
        )


# ---------- Task C4: runbook re-embeds with the api stopped ----------


def test_prod_readme_stops_api_before_reembed() -> None:
    assert "docker compose stop api" in _read(_PROD_README)


def test_prod_readme_reembeds_in_a_one_off_container() -> None:
    text = _read(_PROD_README)
    assert re.search(r"docker compose run --rm --no-deps api python scripts/reembed\.py", text), (
        "README must re-embed via `docker compose run --rm --no-deps api python scripts/reembed.py`"
    )


def test_prod_readme_says_older_image_rejects_local_provider() -> None:
    text = _read(_PROD_README)
    assert re.search(r"dde124e|older image|old image", text)
    assert re.search(r"(?is)(dde124e|older image|old image).{0,300}reject", text) or re.search(
        r"(?is)reject.{0,300}(dde124e|older image|old image)", text
    ), "README must state that an older image rejects EMBEDDING_PROVIDER=local"


def test_compose_comment_mentions_stopping_the_api() -> None:
    assert "docker compose stop api" in _read(_COMPOSE_PATH)
