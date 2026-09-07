# phase-7-evaluation — Evaluation & analytics — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Implement with superpowers:test-driven-development;
> claim completion only via superpowers:verification-before-completion.

**Spec:** `advisordesk-prd.md` §10 Phase 7 — authoritative. Primary sections: §6
(`report_content_gaps` row), §8.1 (eval set), §9.1 (metrics), §10 definition of done. On any
conflict the PRD wins.
**Conventions:** `CONVENTIONS.md` · `docs/FRONTEND-CONVENTIONS.md`.

**Goal:** the analytics story closes the loop: the 9th MCP tool surfaces client questions the
content didn't cover; the groundedness harness scores the assistant against
`seed/eval_questions.yaml` (answer support % + refusal correctness as a summary table); the §9.1
metrics land in the README; and the §10 definition of done is walked end-to-end.

**Architecture:** gap query as a chat-service function wrapped by an MCP tool (same pattern as
every tool); harness as a CLI module driving the real chat path with the real retrieval but a
temperature-0 judge; final verification is a recorded full-gate + demo walk.

**Tech Stack:** existing chat/MCP infrastructure · OpenAI `gpt-4o-mini` (temp 0) as the
groundedness judge (implementation note — PRD doesn't prescribe the judging method).

## Global Constraints

Phase-1..6 Global Constraints apply verbatim (gates, commits, baselines same-commit, no real
OpenAI in tests — the judge is faked in tests, real only in the recorded harness run).

## Tasks

| # | Task | File | Depends on |
|---|------|------|-----------|
| 1 | `report_content_gaps` MCP tool (#9) | `task-01-report-content-gaps.md` | phase-4/task-02, phase-5/task-01 (∥ 2) |
| 2 | Groundedness harness | `task-02-groundedness-harness.md` | phase-4/task-04, phase-4/task-02 |
| 3 | Metrics + final verification | `task-03-metrics-final-verification.md` | 1, 2, phase-6/task-03 |

Order: (1 ∥ 2) → 3. Rationale: tasks 1–2 are independent consumers of phase-4's outcome
recording; task-3 is the closing gate over everything.

## Status

built — snapshot only; git history is authoritative.
