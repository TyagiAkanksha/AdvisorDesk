# video-review-fixes — two small tasks surfaced by the 2026-10-31 demo-video review

Branch `fix/video-review-2026-10` (from main `0acbe54`), carrying cherry-picks of chat-warmth
t01 (`cf00629`, `ab43934`, `7c4f0f7`: the explicit `refusal` flag on the `citations` SSE event,
Opus-reviewed clean on its own branch). Spec: `advisordesk-prd.md` §5.3, §6, §7.5.

| Task | Scope | App | Review |
|---|---|---|---|
| [task-01](task-01-mcp-tool-annotations.md) | Every MCP tool advertises MCP `ToolAnnotations` (`readOnlyHint`, `destructiveHint`) so hosts auto-approve the read tools; `mcp-tools.json` regenerated | api | sonnet |
| [task-02](task-02-client-refusal-sources-and-copy.md) | A refusal never renders Sources (near-miss case); home subtitle names the library; t01 deferred minors M-2/M-4/M-5 | client | sonnet |

Ordering: independent apps; run sequentially in one worktree (never two file-writing agents at
once). Deploy note (t01 M-6): api + client ship together — a new client on an old api drops every
`citations` frame.

Why these two and nothing else: the other review items were settings (AWS alarms/termination
protection/ECR), content (duplicate articles, tag overlap), or video post-production, all done
outside the codebase.
