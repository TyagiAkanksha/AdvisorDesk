# Task 6R-07 — Import-linter contract completions + MCP WebSocket-abort guard

WR-ids: WR-07, t04-M7 (owner: opportunistic, folded here since both touch app/mcp). Effort S. Full
three-agent SDD. Files: `apps/api/pyproject.toml` (contracts), `app/mcp/server.py` (WS guard) + new tests.

## WR-07 — contract gaps (verifier-CORRECTED scope; do NOT use the area report's over-broad list)

The 7 contracts don't fully mechanize CONVENTIONS §2. Real gaps confirmed by the verifier:
- `app.routes` has NO contract → a future `routes → mcp` or `routes → db` direct import (bypassing
  `agent`) is uncaught. Add a forbidden contract: `app.routes` may not import `app.mcp` or `app.db`
  (routes→agent IS legal per the owner-ratified layering; routes reaches mcp *through* agent).
- `app.auth`'s forbidden list omits `app.agent` → add it.
- `app.mcp` → `app.agent` and `app.mcp` → `app.db` are unguarded → add them (extend the existing
  narrow `app.mcp` contract or a new forbidden contract).
Do NOT add `app.mcp`/`app.routes` → `app.main`/`app.factory` — the verifier confirmed contract 7
already covers both. Run CONVENTIONS §2's "contract-verification ritual" for EACH new/widened
contract: deliberately insert the forbidden import, confirm `lint-imports` exits 1 naming it, revert.
Record the ritual output in the report.

## t04-M7 — WebSocket-upgrade abort

`_AdminGatedMcpApp.__call__` constructs `Request(scope)` which asserts `scope["type"]=="http"`; a
`ws://` upgrade to the mount sub-path raises AssertionError → aborted connection + log noise (not a
bypass, but internet-reachable). The existing method-guard (t04 fix) already rejects non-POST before
auth — add: reject `scope["type"] != "http"` early with a clean close/404, BEFORE `Request(scope)`.
Match the existing guard's placement/style in the file.

## Test-author scope (RED, new files only)

- `tests/test_import_contracts_completeness.py`? NO — contracts are verified by the existing
  `test_import_contracts.py` (PINNED — runs `lint-imports`). Instead the RED evidence for WR-07 is
  the ritual (deliberate-violation → exit 1) captured by the implementer; the test-author pins the
  WS guard behaviorally in a NEW `tests/test_mcp_ws_guard.py`: a ws-scope request to the mount path
  returns a clean rejection (not AssertionError/500). Read `test_mcp_gate_fixes.py` for the ASGI-scope
  test pattern (it builds raw scopes). Since the contract change has no pytest RED, state that clearly.

## Constraints & acceptance

Standing rules (env-export pytest, ruff/format-clean, pinned-file stop rule — test_import_contracts.py
+ all registry hashes untouchable). Full suite green env-exported; `lint-imports` 7→ (more) contracts
all KEPT after the additions; ritual evidence for each new contract; wire baselines byte-stable.
Path-scoped adds: pyproject.toml, app/mcp/server.py, new test file. Owner-pending files untouchable.
Commit `feat(api): complete import-linter layer contracts + MCP ws-abort guard (6R-07, WR-07/t04-M7)`.
