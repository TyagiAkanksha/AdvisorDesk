# Task 6R-15 — Provider-aware boot guard + doc cleanup (6R-14 review follow-up)

Blocks the production deploy. From the 6R-14 review (Important): `app/main.py` validates
`NVIDIA_API_KEY` UNCONDITIONALLY in production. Under the new `llm_provider="openai"` default this is
wrong both ways: (a) a missing `OPENAI_API_KEY` boots silently and fails only at first request (guard
defeated); (b) removing the now-unused `NVIDIA_API_KEY` from the prod env **crash-loops boot** — so
the deploy can't drop it. Effort S. Full three-agent SDD; touches the PINNED `test_main_guard.py`
(controller-authorized edit + re-pin).

## Fix (design pins)

1. **`app/main.py`**: replace the unconditional `nvidia_api_key` guard with a PROVIDER-AWARE one —
   in production (`not is_dev`), require the ACTIVE provider's key non-empty:
   `settings.llm_api_key` (the property added in 6R-14). Use a provider-appropriate var NAME in the
   error so the boot failure is actionable: `"OPENAI_API_KEY"` when `settings.llm_provider == "openai"`,
   else `"NVIDIA_API_KEY"`. Keep the dev-exempt behavior (the offline `.env.example` path ships the key
   blank and must still boot; publishing/chat just won't work until it's set — same rationale as today).
   Update the explanatory comment to be provider-neutral.
2. **`tests/test_main_guard.py`** (PINNED — controller-authorized edit, report old→new sha256): update
   the contract to provider-aware:
   - the valid-env baseline sets `OPENAI_API_KEY` (provider defaults to openai); `NVIDIA_API_KEY` is no
     longer required for a clean prod boot.
   - the prod-required-when-blank parametrization tests `OPENAI_API_KEY` (the active key) — blanking it
     under production raises; under development does not.
   - ADD: under `llm_provider="openai"`, blanking `NVIDIA_API_KEY` in production does NOT raise (it's
     inactive). And a `llm_provider="nvidia"` case where blanking `NVIDIA_API_KEY` DOES raise and
     blanking `OPENAI_API_KEY` does not — pins the provider-selection symmetry.
   - keep the unconditional `DATABASE_URL`/`SESSION_SECRET` + `GOOGLE_*`/`ADMIN_EMAILS` cases intact.
   These are assertion CHANGES (the contract legitimately changed), not just data — that's why it's
   controller-authorized and re-pinned. Touch no unrelated assertion.
3. **Doc Minors (4, from the review)**: refresh stale "NVIDIA NIM client" prose in
   `app/rag/synthesis.py:1,63`, `app/rag/embeddings.py:43`, `app/agent/llm.py:9,24,119` to
   provider-neutral wording (non-functional; fold in here).

## Gates & acceptance

env-exported full suite green (expect 524 + any net new guard tests); ruff --no-cache/format/mypy/
lint-imports clean; wire baselines byte-stable. Verify BOTH directions by reasoning + tests: prod +
provider=openai + blank OPENAI key → boot RAISES naming OPENAI_API_KEY; prod + provider=openai +
present OPENAI key + absent NVIDIA key → boots clean (this is the deploy-safety property). Path-scoped
adds: `app/main.py`, `tests/test_main_guard.py`, and the 3 doc-only source files. Do NOT touch `.env`.
Commit `fix(api): provider-aware boot-key guard + provider-neutral docs (6R-15, 6R-14 review)`.

## Why it gates prod

The production deploy sets `LLM_PROVIDER=openai` + `OPENAI_API_KEY`. Without this fix the box's env
MUST retain a non-empty `NVIDIA_API_KEY` placeholder or boot crash-loops, and a genuinely missing
OpenAI key wouldn't be caught at boot. This fix makes the deploy validate the credential actually in
use. Merge this before the prod redeploy.
