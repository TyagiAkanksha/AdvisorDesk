# Suggestions

Enhancements and ideas noticed during implementation that are out of scope for the current task —
never scope expansion, always a follow-up note (PRD §11 implementer contract).

- Migrate `apps/api`'s dev dependency from `httpx` to `httpx2` for `fastapi.testclient.TestClient`
  — starlette 1.x deprecates `httpx` there (task-03); `httpx` stays for now since CONVENTIONS.md
  §9 names it explicitly and swapping it is a conventions-level change, not a task-scoped one.
