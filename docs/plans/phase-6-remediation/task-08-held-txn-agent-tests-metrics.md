# Task 6R-08 — Held-open transaction fix + agent-route error tests + metrics bucket split

WR-ids: WR-09, WR-10, t01-N2 (owner: fix). Effort S-M. Full three-agent SDD. Three related backend
items in `app/routes/`; disjoint from 6R-07/09/10 source files.

## WR-09 — transaction held across the LLM stream

`/public/chat` (`app/routes/public_routes.py`) holds a Postgres txn open from the retrieval SELECT
through the entire token-streaming loop to the post-stream commit. Read the current
`_generate_chat_stream`/exchange flow first. Fix: commit the user-message write (and release the txn)
BEFORE the LLM streaming loop begins; the assistant-message write + its commit happen after the
stream as today. Preserve: the pinned ordering guarantees (created_at ordering — p4-t02 pinned that
the user row commits before the assistant row), the §4 error-event atomicity, and the SSE carve-out.
This must NOT weaken any pinned public-chat test. If the ordering pins make a clean split impossible,
STOP + NEEDS_CONTEXT rather than touching a pinned test.

## WR-10 — agent-route HTTP-level error-path tests

`/agent/chat`'s SSE-error-render + outer-exception paths (agent_routes.py ~66, ~103-115) have no
HTTP-level coverage; public_chat has the exact sibling test. Add (test-author) the direct analog of
`test_llm_failure_mid_stream_emits_error_event_and_still_persists_user_message` for the agent route:
a real `POST /agent/chat` driving (a) an Error event reaching the wire via the fallback, and (b) an
exception escaping `run_agent` through the outer except. Expected: no production change needed (the
handler already works — this closes a coverage gap); if a test surfaces a real bug, that's a genuine
GREEN fix.

## t01-N2 — metrics bucket split

`_route_name` (`app/routes/metrics.py`) lumps MCP `Mount` POSTs into the `"unmatched"` bucket with
404 scans, mixing their latency percentiles. Give Mount sub-paths their own bucket key (e.g.
`mount:<path>`), leaving genuine 404s in `"unmatched"`. Keep the public `snapshot()` shape stable;
the constant-key cardinality property (t01 I-1 fix) must hold — Mount paths are bounded, so this adds
O(1) keys, not unbounded ones. Pin it: a request to the MCP mount buckets separately from a 404.

## Test-author / constraints / acceptance

New files only (e.g. `tests/test_public_chat_txn.py`, agent-route test into a new file, metrics bucket
into a new file — or one combined new file with clear sections). Standing rules apply (env-export,
ruff/format-clean, pinned-file stop rule). Full suite green env-exported; wire baselines byte-stable;
path-scoped adds (public_routes.py, metrics.py, new test files — agent_routes.py only if WR-10 finds a
real bug). Owner-pending files untouchable. Commit
`feat(api): release chat txn before stream + agent-route error tests + metrics mount bucket (6R-08, WR-09/WR-10/t01-N2)`.
