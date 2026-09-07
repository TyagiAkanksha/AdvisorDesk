# phase-3-publish-client-content — Publish pipeline + client content — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Implement with superpowers:test-driven-development;
> claim completion only via superpowers:verification-before-completion.

**Spec:** `advisordesk-prd.md` §10 Phase 3 — authoritative. Primary sections: §4 (lifecycle rule +
atomicity), §7.1–§7.2 (chunking, embedding), §5.3 (public content), §2.2 (client stories). On any
conflict the PRD wins.
**Conventions:** `CONVENTIONS.md` · `docs/FRONTEND-CONVENTIONS.md`.

**Goal:** publishing becomes real — chunk, embed, insert in one transaction with rollback on
embedding failure — and clients can browse published content: public list/detail API plus the
client app's server-rendered content pages. After this phase, the §4 guarantee holds: retrieval
(phase 4) can only ever see currently-published, non-deleted, fully-embedded content.

**Architecture:** pure chunking module; `Embedder` protocol wrapping OpenAI embeddings; a real
`ChunkPipeline` implementation swapped into the phase-2 seam via factory wiring (service
signatures untouched); public routes with their own DTOs; client app fetches server-side (RSC).

**Tech Stack:** tiktoken (token counting — implementation note) · `nvidia/nv-embedqa-e5-v5`
(1024d) over NVIDIA NIM's OpenAI-compatible `/v1/embeddings` endpoint (v1.5; superseded the
original `text-embedding-3-small` plan) · react-markdown + remark-gfm over MUI Typography.

## Global Constraints

Phase-1/2 Global Constraints apply verbatim (gates, commits, wire-surface same-commit gate,
soft-delete visibility, PRD defaults philosophy).

- The §4 atomicity rule is non-negotiable: a partial chunk set must never be observable — every
  lifecycle mutation runs in a single transaction and rolls back wholly on embedding failure.
- The real OpenAI embedder is never called in tests — the `Embedder` protocol seam is.

## Tasks

| # | Task | File | Depends on |
|---|------|------|-----------|
| 1 | Chunking module | `task-01-chunking.md` | phase-1 |
| 2 | Embeddings + transactional lifecycle | `task-02-embedding-lifecycle.md` | 1, phase-2/task-02 |
| 3 | Public content API | `task-03-public-content-api.md` | phase-2/task-03 (∥ 1–2) |
| 4 | Client app content UI | `task-04-client-content-ui.md` | phase-1/task-04, 3 |

Order: (1 → 2) ∥ 3, then 4. Rationale: task-02 fills the phase-2 seam and pins the chunk-row
shape retrieval (phase 4) reads; task-03 pins the public DTOs task-04 renders.

## Status

built — snapshot only; git history is authoritative.
