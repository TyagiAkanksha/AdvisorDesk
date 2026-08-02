"""The in-process MCP invocation seam (task-01 brief, PRD §3/§6).

`call_tool`/`list_tool_schemas` are the ONE place a tool name resolves to
behavior — the agent loop (task-03) calls them directly with no HTTP
involved, and `app.mcp.server`'s streamable-HTTP transport (when
`MCP_HTTP_ENABLED=true`) delegates to the exact same two functions for
`tools/call`/`tools/list`, so a tool behaves identically regardless of
caller. `scripts/export_mcp_tools.py` (the committed `mcp-tools.json`
baseline) also reads `list_tool_schemas()`.

Registration pattern (task-02's six write tools follow this): a module
under `app.mcp` (this task's `tools_read.py`) builds a
`tuple[ToolSpec, ...]` — one `ToolSpec` per tool, each pairing a Pydantic
args model with a `session`+`actor_id`-taking handler that calls straight
into `app.services.*` — and this module's `_ALL_TOOLS` assembles every
module's tuple into the one registry `call_tool`/`list_tool_schemas` read.
Adding a tool module means adding one entry to `_ALL_TOOLS` here; nothing
else in this file changes.

Phase-5 task-02: `call_tool` gained a keyword-only `pipeline` parameter — the
`ChunkPipeline` seam `app.mcp.tools_write`'s write tools embed chunks
through (publish/archive/delete/edit-of-published-item, PRD §4). It is
optional, defaulting to `NoopChunkPipeline()` when omitted (mirroring
`app.factory.create_app`'s own `chunk_pipeline: ChunkPipeline | None = None`
default), and reaches write-tool handlers via `session.info` rather than a
new handler argument — see `app.mcp.tool_spec.SESSION_INFO_PIPELINE_KEY`
and `app.mcp.tools_write`'s module docstring for why: the handler-call shape
right below (`spec.handler(args, session=session, actor_id=actor_id)`) is
pinned by `tests/test_mcp_runtime_guards.py`/`tests/test_mcp_read_tools.py`
and must not change.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.mcp.tool_spec import SESSION_INFO_PIPELINE_KEY, ToolSpec
from app.mcp.tools_read import READ_TOOLS
from app.mcp.tools_write import WRITE_TOOLS
from app.services.errors import ToolInputError, ToolNotFoundError
from app.services.lifecycle import ChunkPipeline, NoopChunkPipeline

__all__ = ["ToolSpec", "call_tool", "list_tool_schemas"]

# Every registered tool, module-by-module.
_ALL_TOOLS: tuple[ToolSpec, ...] = (*READ_TOOLS, *WRITE_TOOLS)

_REGISTRY: dict[str, ToolSpec] = {tool.name: tool for tool in _ALL_TOOLS}


def _format_validation_error(exc: ValidationError) -> str:
    """Render a `ValidationError` as `"field: message; field2: message2"`.

    Mirrors `app.routes.errors._validation_error_handler`'s `loc: msg`
    shape (module docstring on `ToolInputError`) — every failing field is
    named, never the raw offending value (same information-hygiene reason
    that handler avoids `input`/`ctx`).
    """
    parts: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(segment) for segment in error["loc"])
        parts.append(f"{loc}: {error['msg']}" if loc else error["msg"])
    return "; ".join(parts) if parts else "invalid arguments"


def call_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    session: Session,
    actor_id: uuid.UUID,
    pipeline: ChunkPipeline | None = None,
) -> dict[str, Any]:
    """Validate `arguments` via `name`'s args model, run its handler, return the JSON payload.

    Args:
        name: the tool name to invoke (PRD §6 tool table).
        arguments: raw, caller-supplied keyword arguments — validated
            before the handler ever sees them.
        session: the caller's `Session` (in-process: the agent loop's own;
            over HTTP: one opened for this request by `app.mcp.server`).
        actor_id: the authenticated admin driving this call (PRD §4.1
            actor-column stamping on any write tool).
        pipeline: the `ChunkPipeline` a write tool (`app.mcp.tools_write`)
            embeds chunks through. `None` (the default — every read-tool
            call, and any write-tool call that doesn't supply one) resolves
            to `NoopChunkPipeline()`. Stashed on `session.info` (not passed
            to `spec.handler` directly) so this stays a purely additive
            change to this function's own signature — see the module
            docstring. Popped again once `handler` returns or raises (fix
            round 1, finding M7), so `session.info` never holds a stale
            pipeline reference from a previous call.

    Returns:
        The tool's structured JSON-able payload.

    Raises:
        ToolNotFoundError: `name` is not a registered tool.
        ToolInputError: `arguments` fails `name`'s args-model validation —
            the message names every offending field.
    """
    spec = _REGISTRY.get(name)
    if spec is None:
        raise ToolNotFoundError(f"Unknown MCP tool {name!r}.")
    try:
        args = spec.args_model.model_validate(arguments)
    except ValidationError as exc:
        raise ToolInputError(_format_validation_error(exc)) from exc
    session.info[SESSION_INFO_PIPELINE_KEY] = (
        pipeline if pipeline is not None else NoopChunkPipeline()
    )
    try:
        return spec.handler(args, session=session, actor_id=actor_id)
    finally:
        session.info.pop(SESSION_INFO_PIPELINE_KEY, None)


def list_tool_schemas() -> list[dict[str, Any]]:
    """Return `{name, description, inputSchema}` for every registered tool.

    Feeds the agent loop (task-03, which model the tool schemas are given
    to) and `scripts/export_mcp_tools.py`'s committed baseline. Internal
    schema-field shape is deliberately not pinned by any test beyond "some
    dict-shaped field besides name/description" (controller decision, see
    `tests/test_mcp_read_tools.py`) — `inputSchema` is used here because
    it's the MCP wire protocol's own field name for it.
    """
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.args_model.model_json_schema(),
        }
        for tool in _ALL_TOOLS
    ]
