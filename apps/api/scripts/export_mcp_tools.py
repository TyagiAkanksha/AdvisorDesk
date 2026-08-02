"""Dump every registered MCP tool's schema to `mcp-tools.json` (CONVENTIONS.md §8).

Deterministic output (`sort_keys=True`, indent 2, trailing newline) so
`git diff --exit-code mcp-tools.json` proves the MCP wire surface did not
move. Standing gate from task-01 onward: any commit that changes a tool's
name/description/args model regenerates this file in the same commit
(CONVENTIONS.md §8, task-01 brief).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.mcp.runtime import list_tool_schemas

_OUTPUT_PATH = Path(__file__).resolve().parent.parent / "mcp-tools.json"


def main() -> None:
    """Write every registered tool's `{name, description, inputSchema}` deterministically."""
    payload = list_tool_schemas()
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    _OUTPUT_PATH.write_text(text)


if __name__ == "__main__":
    main()
