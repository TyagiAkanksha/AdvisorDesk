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

import types
import uuid
from typing import Any, get_args, get_origin

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.mcp.tool_spec import SESSION_INFO_PIPELINE_KEY, ToolSpec
from app.mcp.tools_gaps import GAPS_TOOLS
from app.mcp.tools_read import READ_TOOLS
from app.mcp.tools_write import WRITE_TOOLS
from app.services.errors import ToolInputError, ToolNotFoundError
from app.services.lifecycle import ChunkPipeline, NoopChunkPipeline

__all__ = ["ToolSpec", "call_tool", "list_tool_schemas"]

# Every registered tool, module-by-module.
_ALL_TOOLS: tuple[ToolSpec, ...] = (*READ_TOOLS, *WRITE_TOOLS, *GAPS_TOOLS)

_REGISTRY: dict[str, ToolSpec] = {tool.name: tool for tool in _ALL_TOOLS}


def _describe_example(annotation: Any) -> tuple[str, str] | None:
    """Return `(type description, literal example)` for a field's type annotation, or `None`.

    Checkpoint fix (finding L-1, task-03 brief pin): the pinned model (meta/llama-3.1-8b-instruct)
    self-corrects a bad tool-call argument ONLY when the fed-back error shows the EXPECTED shape
    with a literal example — a field-name-only message or a schema-description example both fail
    (probe-established fact, 2026-08-01, ledger). Derived generically from the annotation (list of
    strings, int, str, bool, ...) rather than special-cased to any one field (e.g. `tags`), so any
    args model's field gets the same treatment.

    Recurses once through `X | None` (every optional field in `app.mcp`'s args models uses this
    form) to describe the non-`None` member. Returns `None` for an annotation this doesn't
    recognize (e.g. `uuid.UUID`) — the caller falls back to the plain `"field: message"` shape
    for those, exactly as before this fix.
    """
    origin = get_origin(annotation)
    if origin is types.UnionType:
        non_none = [arg for arg in get_args(annotation) if arg is not type(None)]
        return _describe_example(non_none[0]) if non_none else None
    if origin is list:
        item_types = get_args(annotation)
        item_type = item_types[0] if item_types else str
        if item_type is str:
            return ("a JSON array of strings", '["example"]')
        if item_type is int:
            return ("a JSON array of integers", "[1, 2, 3]")
        return ("a JSON array", "[...]")
    if annotation is bool:
        return ("a boolean", "true")
    if annotation is int:
        return ("an integer", "10")
    if annotation is float:
        return ("a number", "3.14")
    if annotation is str:
        return ("a string", '"example"')
    return None


def _field_hint(model: type[BaseModel], loc: tuple[int | str, ...]) -> str | None:
    """Build the `"Expected <type>, e.g. <example>."` suffix for one `ValidationError` error.

    Looks up only the TOP-LEVEL field (`loc[0]`) — every args model under `app.mcp` is flat (no
    nested `BaseModel` fields), so this is the whole field path. Returns `None` when `loc[0]`
    doesn't name a field on `model` (e.g. `extra="forbid"`'s unknown-argument errors — `loc[0]`
    there names whatever the CALLER sent, not a real field) or the annotation isn't a recognized
    shape (`_describe_example`); the caller falls back to the base message alone either way.
    """
    if not loc or not isinstance(loc[0], str):
        return None
    field_info = model.model_fields.get(loc[0])
    if field_info is None:
        return None
    described = _describe_example(field_info.annotation)
    if described is None:
        return None
    type_desc, example = described
    return f"Expected {type_desc}, e.g. {example}."


def _format_validation_error(exc: ValidationError, model: type[BaseModel]) -> str:
    """Render a `ValidationError` as `"field: message[ Expected <type>, e.g. <example>.]; ..."`.

    The base `"field: message"` shape mirrors `app.routes.errors._validation_error_handler`'s
    `loc: msg` shape (module docstring on `ToolInputError`) exactly as before — every failing
    field is named, never the raw offending value (same information-hygiene reason that handler
    avoids `input`/`ctx`). The appended sentence (`_field_hint`) is the checkpoint fix (finding
    L-1): it makes the message actionable enough for the agent loop's one-shot self-correction
    retry (PRD §6) to succeed against the pinned model's known first-shot habits. No input
    coercion happens anywhere in this path — validation stays strict; this only changes what the
    rejection message SAYS.
    """
    parts: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(segment) for segment in error["loc"])
        base = f"{loc}: {error['msg']}" if loc else error["msg"]
        hint = _field_hint(model, error["loc"])
        parts.append(f"{base} {hint}" if hint else base)
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
        raise ToolInputError(_format_validation_error(exc, spec.args_model)) from exc
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
