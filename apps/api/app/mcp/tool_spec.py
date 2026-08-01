"""`ToolSpec` — one registered MCP tool's shape (name, args model, handler).

Split out from `app.mcp.runtime` (which assembles every tool module's
`ToolSpec`s into the registry `call_tool`/`list_tool_schemas` read) so a
tool module (this task's `tools_read.py`; task-02's `tools_write.py`) can
import `ToolSpec` without importing `runtime` itself — `runtime` is the one
that imports the tool modules, so the reverse import would be circular.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class ToolSpec:
    """One registered MCP tool: its wire name/description, args model, and handler.

    Args:
        name: the tool name callers address via `call_tool`/the MCP wire
            protocol (PRD §6 tool-table names, e.g. `"search_content"`).
        description: a human/model-readable summary — surfaced verbatim in
            `list_tool_schemas()` and the MCP `tools/list` response.
        args_model: the Pydantic model `arguments` is validated against
            before `handler` ever runs.
        handler: `(args, *, session, actor_id) -> dict[str, Any]` — the
            tool's behavior. Typed `Callable[..., ...]` (not a precise
            per-tool `Callable[[ArgsT], ...]`) deliberately: `Callable`
            parameter types are contravariant, so a registry of handlers
            with different concrete `args_model` subclasses can't share one
            covariant `Callable[[SomeBaseModel], ...]` annotation without
            each individual handler failing that check; `...` is the
            standard escape for a heterogeneous callback registry.
    """

    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[..., dict[str, Any]]
