---
id: task-03
phase: phase-4-rag-assistant
depends_on: [task-02]
status: planned
spec: advisordesk-prd.md §9 (rate limiting), §5.3
---

# task-03 — Rate limiting for the public chat surface

## Goal

The three §9 caps are enforced in-app with an injectable clock: `RATE_LIMIT_PER_MIN` per IP,
`RATE_LIMIT_PER_DAY` per session, `SESSION_CREATE_PER_DAY` per IP (the cap that stops
fresh-session minting). Violations return plain-JSON 429 with the standard envelope before any
stream opens.

## Context (read ONLY these)

- `advisordesk-prd.md` §9 "Rate limiting" (the three caps + defaults; in-memory store explicitly
  acceptable for a single container), §5.3 (session creation is "subject to the per-IP creation
  cap").
- `app/routes/public_routes.py` + `app/services/chat.py` (task-02) — the integration points.

## Files

- Create: `apps/api/app/routes/ratelimit.py`
- Create: `apps/api/tests/test_ratelimit.py`
- Modify: `apps/api/app/routes/public_routes.py` (wire the dependency),
  `apps/api/app/services/errors.py` (`RateLimitedError` already exists — confirm mapping to 429)

## Interfaces

- **Consumes:** `Settings` caps; `RateLimitedError` → 429 mapping (p1-t03).
- **Produces (later tasks rely on — produce exactly):**
  - `app.routes.ratelimit`: `class RateLimiter` —
    `__init__(settings, clock: Callable[[], float] = time.monotonic)`;
    `check_message(ip: str, session_id: str | None) -> None` (raises `RateLimitedError` on
    per-min/IP or per-day/session breach); `check_session_create(ip: str) -> None`;
    `note_session_created(ip: str)`. Sliding one-minute window; day buckets reset at UTC
    midnight (implementation note). Instance on `app.state.rate_limiter`.
  - Wiring order pin: limits checked **before** `get_or_create_session` and before the SSE
    response starts; a rejected request is plain JSON 429, not an `error` event.
  - **Phase-6 task-02 verifies these same caps in the deployed environment.**

## Steps (TDD)

- [ ] **Step 1: Failing unit tests** (`test_ratelimit.py`, fake clock — no HTTP): 10 messages in
  a minute from one IP pass, the 11th raises; advancing the clock 61s admits again; per-day/
  session: 50 pass, 51st raises regardless of pacing; session-create: 20 pass, 21st raises,
  other IPs unaffected; caps read from `Settings` (a custom `Settings(rate_limit_per_min=2)`
  trips at 3).
- [ ] **Step 2:** run → FAIL. **Step 3: implement** `RateLimiter`. **Step 4:** run → PASS.
- [ ] **Step 5: Failing endpoint tests** (extend `test_ratelimit.py`, TestClient with tight
  custom caps): breach → HTTP 429 with `{"error":{"code":"rate_limited",...}}` and
  `content-type: application/json` (not an event stream); under-cap requests still stream;
  minting sessions past the create-cap → 429 (**the §9 anti-reset pin**).
- [ ] **Step 6:** run → FAIL → wire dependency → PASS.
- [ ] **Step 7: Gates → commit:** `feat(api): public chat rate limiting (phase-4 task-03)`

## Verify

```bash
cd apps/api
uv run pytest tests/test_ratelimit.py -q       # unit part passes with no DB
TEST_DATABASE_URL=... uv run pytest tests/test_ratelimit.py -q   # endpoint part too
for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST localhost:8000/api/v1/public/chat -H 'content-type: application/json' \
  -d '{"message":"hi"}'; done    # 200s then 429s once the per-min cap trips
```

## Acceptance

- All three §9 caps enforced with their PRD defaults, env-tunable, injectable clock (no sleeps in
  tests).
- 429s carry the standard envelope as plain JSON before any stream begins.
- The session-mint loophole is closed and pinned by test.
