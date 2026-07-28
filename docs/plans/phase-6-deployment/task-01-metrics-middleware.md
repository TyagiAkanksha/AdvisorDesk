---
id: task-01
phase: phase-6-deployment
depends_on: [phase-4-rag-assistant/task-02]
status: planned
spec: advisordesk-prd.md §9 (streaming latency), §9.1
---

# task-01 — Metrics middleware: first-token latency p50/p95

## Goal

Request timing and — specifically — time-to-first-`token`-event on `/public/chat` are measured
with an injectable clock and logged as rolling p50/p95 (§9 "a simple middleware logs p50/p95").
This produces the §9.1 latency metric phase-7 captures into the README.

## Context (read ONLY these)

- `advisordesk-prd.md` §9 "Streaming latency" (target < ~2s first token; log-based) and §9.1.
- `app/routes/sse.py` + `public_routes.py` (p4-t02) — wrap, don't modify event semantics.
- **Implementation note:** metrics are exposed via logs only — no new endpoint; the §5 surface
  stays frozen.

## Files

- Create: `apps/api/app/routes/metrics.py`
- Create: `apps/api/tests/test_metrics.py`
- Modify: `apps/api/app/factory.py` (install middleware), `apps/api/app/routes/sse.py` (hook:
  optional `on_first_event` callback on `sse_response`)

## Interfaces

- **Consumes:** SSE utilities; settings; logging config.
- **Produces (later tasks rely on — produce exactly):**
  - `app.routes.metrics`: `class LatencyTracker` —
    `__init__(clock: Callable[[], float] = time.monotonic, window: int = 500)`;
    `observe(route: str, seconds: float)`; `snapshot() -> dict[str, {p50, p95, count}]`
    (nearest-rank percentiles over the rolling window).
  - ASGI middleware logging one structured line per request
    (`route, status, duration_ms`) and, for `public_chat`, `first_token_ms` via the
    `on_first_event` hook; every 100 chat requests logs
    `chat_latency p50=<ms> p95=<ms> count=<n>` — **the line format phase-7 task-03 greps for the
    §9.1 metric.**
  - Instance on `app.state.latency_tracker` (tests can read `snapshot()` directly).

## Steps (TDD)

- [ ] **Step 1: Failing tracker unit tests** (`test_metrics.py`, fake clock, no HTTP): known
  sequence (100 observations 10..1000ms) → exact nearest-rank p50/p95; rolling window evicts
  oldest; empty tracker snapshot → `{}`.
- [ ] **Step 2:** run → FAIL. **Step 3: implement** `LatencyTracker` + percentile math.
  **Step 4:** run → PASS.
- [ ] **Step 5: Failing wiring tests**: TestClient chat request (fake LLM) → tracker observed a
  `public_chat` first-token sample > 0; a plain `GET /healthz` → request sample but no
  first-token sample; log line format matches
  `chat_latency p50=\d+ p95=\d+ count=\d+` (caplog).
- [ ] **Step 6:** run → FAIL → **implement** middleware + sse hook → PASS. Confirm event
  payloads unchanged (existing p4-t02 tests stay green).
- [ ] **Step 7: Gates → commit:** `feat(api): latency metrics middleware (phase-6 task-01)`

## Verify

```bash
cd apps/api
TEST_DATABASE_URL=... uv run pytest tests/test_metrics.py tests/test_public_chat.py -q  # both green
uv run python scripts/export_openapi.py && git diff --exit-code openapi.json  # surface unchanged
```

## Acceptance

- First-token latency measured on `/public/chat` only; general timing on all routes; percentile
  math unit-tested with an injectable clock (no sleeps).
- No new/changed routes (baseline diff empty); §5.3 event stream byte-compatible.
- The greppable `chat_latency` log line exists for §9.1 capture.
