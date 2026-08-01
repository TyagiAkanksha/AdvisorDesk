# phase-4-rag-assistant — RAG assistant — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Implement with superpowers:test-driven-development;
> claim completion only via superpowers:verification-before-completion.

**Spec:** `advisordesk-prd.md` §10 Phase 4 — authoritative. Primary sections: §7 (pipeline, incl.
the §7.3 similarity trap), §5.3 (`POST /public/chat` + SSE events), §4 (citation-granularity
asymmetry), §8 + §8.1 (seed + eval set), §9 (rate limits). On any conflict the PRD wins.
**Conventions:** `CONVENTIONS.md` · `docs/FRONTEND-CONVENTIONS.md`.

**Goal:** a client asks a question and gets a streamed, cited answer grounded ONLY in published
content — or an explicit refusal when nothing clears the threshold — with retrieval outcomes
recorded per §7.4, rate limits enforced per §9, the seed corpus + eval questions authored (§8),
and the client chat UI live.

**Architecture:** retrieval module owns the similarity convention (defined once); synthesis
behind an injectable LLM seam; one SSE utility module shared with `/agent/chat`; rate limiting as
route dependencies with an in-memory store; chat UI as a client-side island over a hand-rolled
SSE reader.

**Tech Stack:** pgvector HNSW `<=>` · NVIDIA OpenAI-compatible API (v1.5, `LLM_BASE_URL`):
**`CHAT_MODEL` = `meta/llama-3.1-8b-instruct`** (the PRD §7 "pinned in the phase-4 plan" pin —
probe-verified 2026-07-31: 0.36s e2e / 28ms first token on the free tier, correct
context-only + refusal behavior, SSE streaming confirmed; the 70B variant queued 49–73s and is
disqualified for the public path) + query embeddings through the existing phase-3 `Embedder`
(`nvidia/nv-embedqa-e5-v5`, `input_type="query"` — the asymmetric twin of publish-time
`"passage"`) · SSE over fetch/ReadableStream · localStorage sessions.

## Global Constraints

Phase-1/2/3 Global Constraints apply verbatim (gates, commits, wire-surface same-commit gate,
soft-delete visibility, PRD defaults philosophy, no real LLM-provider calls in tests — the
`Embedder`/`ChatLLM` seams take fakes, exactly as phase 3 did).

- **§7.3 similarity trap:** pgvector `<=>` returns cosine *distance*; `similarity = 1 - distance`
  is defined once in `app/rag/retrieval.py` and the pin test locks it. Nothing else computes it.
- **Citation asymmetry (§4):** DB rows store chunk-level citations; the public wire is deduped to
  content level. Both code sites carry the explaining comment the PRD demands.
- The assistant must never answer from general knowledge — the refusal path is a feature, tested
  as such.

## Tasks

| # | Task | File | Depends on |
|---|------|------|-----------|
| 1 | Retrieval + similarity convention | `task-01-retrieval.md` | phase-3/task-02 |
| 2 | Chat endpoint: synthesis + SSE + persistence | `task-02-chat-synthesis-sse.md` | 1 |
| 3 | Rate limiting | `task-03-rate-limiting.md` | 2 |
| 4 | Seed articles + eval question set | `task-04-seed-content-eval-set.md` | phase-3/task-02 (∥ 1–3) |
| 5 | Client chat UI | `task-05-client-chat-ui.md` | 2, phase-3/task-04 |

Order: 1 → 2 → 3 → 5, with 4 parallel throughout (it needs only the phase-3 pipeline). Rationale:
task-01 pins `RetrievedChunk`/similarity semantics task-02 consumes; task-02 pins the SSE utility
+ event shapes that task-05 parses and phase-5's agent endpoint reuses.

## ⚠️ Controller checkpoint — after task-05

When task-05's gates pass, PAUSE for the user's live pass of the client chat (ask a covered
question → cited streamed answer; ask an uncovered one → refusal; hammer the limiter → friendly
429). Use superpowers:requesting-code-review for the phase diff. Do not skip.

## Status

planned — snapshot only; git history is authoritative.
