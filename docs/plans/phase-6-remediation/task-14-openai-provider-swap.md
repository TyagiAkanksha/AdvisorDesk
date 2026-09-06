# Task 6R-14 — LLM provider switch to OpenAI (restore chat: both NVIDIA models EOL'd)

Critical path — production chat outage. Both pinned NVIDIA models are end-of-life (410 Gone):
`nvidia/nv-embedqa-e5-v5` (embedding, 2026-08-25) and `meta/llama-3.1-8b-instruct` (chat, 2026-08-26).
Owner chose OpenAI (key `OPENAI_API_KEY` already in `.env`). Controller-verified live:
`text-embedding-3-small` with `dimensions:1024` returns exactly 1024-dim vectors (**drop-in — matches
the existing `chunks.embedding vector(1024)` column + HNSW index, NO migration**); `gpt-4o-mini`
responds and supports tool-calling (the admin agent needs it). Effort M. Full three-agent SDD; the
wire contract legitimately changes, so pinned wire-test edits are pre-authorized (controller re-pins).

## Why it's not pure config

The architecture promised "provider swap never touches code," but NVIDIA-specific params leaked into
the embedding request. `app/rag/embeddings.py::embed_texts` sends
`extra_body={"input_type": ..., "truncate": "END"}` and does **not** send `dimensions`. OpenAI's
`/v1/embeddings` **rejects** `input_type`/`truncate` and **requires** `dimensions` to output 1024
(default is 1536). The chat client (`app/agent/llm.py`, `app/rag/synthesis.py`) sends no
NVIDIA-specific params → clean. The credential field `nvidia_api_key` (env `NVIDIA_API_KEY`) is used
for BOTH and must pick up the OpenAI key.

## Design pins (controller)

1. **config.py**: add `openai_api_key: SecretStr = SecretStr("")` (env `OPENAI_API_KEY`); add
   `llm_provider: Literal["openai", "nvidia"] = "openai"`; add a property `llm_api_key` returning the
   openai key when provider==openai else the nvidia key. KEEP `nvidia_api_key` (back-compat). Update
   DEFAULTS: `llm_base_url = "https://api.openai.com/v1"`, `embedding_model = "text-embedding-3-small"`,
   `chat_model = "gpt-4o-mini"`, `embedding_dimensions = 1024` (unchanged). The empty-key `"unset"`
   boot-safety fallback pattern stays (dev boots with no key).
2. **embeddings.py**: `from_settings` builds the client with `settings.llm_api_key`; pass the provider
   (or a boolean "openai-style request") into the embedder. `embed_texts`: when openai, send
   `dimensions=self._dimensions` and NO `extra_body` (input_type is meaningless for OpenAI's symmetric
   model — accept the param, ignore it); when nvidia, the current shape (extra_body input_type/truncate,
   no dimensions). Keep `encoding_format="float"` both. The response-count + per-vector-dim validation
   at the seam is unchanged.
3. **Chat (llm.py + synthesis.py)**: `from_settings` uses `settings.llm_api_key`. No param change.
4. **main.py boot checks**: the embedding-dims assertion (1024) is unchanged; confirm the boot env
   validation still passes with the new provider defaults (and that a missing OPENAI key when
   provider=openai is handled the same boot-safe way as the old nvidia empty-key path).
5. **PRD**: amend §7.2 (v1.6): provider is config-driven, defaults now OpenAI
   (`text-embedding-3-small`@1024, `gpt-4o-mini`), with a dated note that the NVIDIA NIM models were
   EOL'd; the asymmetric input_type/passage-query detail is now NVIDIA-branch-specific. Changelog entry.
6. **.env.example**: add `OPENAI_API_KEY`, `LLM_PROVIDER=openai`, and the new model/base-url defaults;
   note NVIDIA_API_KEY is only needed when `LLM_PROVIDER=nvidia`.

## Test-author scope (RED, new files + pre-authorized pinned edits)

- NEW `tests/test_openai_embeddings_wire.py`: with provider=openai, `embed_texts` sends a request body
  with `model`, `input`, `encoding_format="float"`, **`dimensions=1024`**, and **NO `extra_body`/
  input_type/truncate** (MockTransport capture, mirror the existing `test_embeddings_client.py` style).
- NEW `tests/test_llm_provider_config.py`: `llm_provider` selects `llm_api_key` correctly; defaults are
  the OpenAI values; openai key empty → boot-safe.
- Chat: a wire test confirming the chat client authenticates with the OpenAI key and sends standard
  chat-completions (extend the existing pattern in a NEW file).
- The EXISTING pinned wire tests (`test_embeddings_client.py` NVIDIA-shape, `test_agent_llm_client.py`)
  become provider-parameterized or explicitly the `provider="nvidia"` case — controller PRE-AUTHORIZES
  editing these pinned files to keep the NVIDIA-shape assertions valid under an explicit nvidia provider
  (assertion-preserving: the NVIDIA branch still sends exactly what it sent). Report the diffs + new
  sha256 for controller re-pin; touch no NVIDIA-shape ASSERTION beyond gating it behind provider=nvidia.

## Gates & acceptance

env-exported (`export "$(grep '^TEST_DATABASE_URL=' /home/ak/Documents/github_akanksha/AdvisorDesk/.env | tr -d '\r')"`, container :5433). Full suite green; ruff --no-cache/format/mypy/lint-imports clean;
wire baselines (`openapi.json`/`mcp-tools.json`) byte-stable (no route/DTO change). Do NOT make live
provider calls in tests (MockTransport only — the standing rule). Path-scoped adds. Owner-pending: tree
is clean now; `.env` is the owner's (do not commit it — it holds the real OpenAI key; only `.env.example`
is tracked). Commit `feat(api): config-driven LLM provider + OpenAI defaults (6R-14, chat restore)`.

## After this task (SEPARATE ops step, controller+owner)

Re-embed the corpus with OpenAI (local verify: re-seed against a fresh local DB, run a real
`/public/chat` → grounded cited answer; verify the admin agent tool-calling with gpt-4o-mini) → then
prod: put `OPENAI_API_KEY` into SSM, set `LLM_PROVIDER=openai` + new model env on the api container,
FORCE a corpus re-embed (existing NVIDIA vectors are model-specific and must be regenerated — unpublish→
republish or a re-embed pass; seed idempotency alone will NOT re-embed), redeploy, VERIFY live. THEN
WR-18 (6R-13) demo unblocks. Tracked in 00-INDEX.
