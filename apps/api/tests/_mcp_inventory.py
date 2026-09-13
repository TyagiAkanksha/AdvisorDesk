"""Single-sourced MCP tool-name inventory for test files (fix wave D4; t16-review M6).

The registry's fourteen tool names were duplicated as a hand-copied literal set in three test
files (`test_mcp_bearer_auth.py`, `test_oauth_e2e_flow.py`, `test_agent_loop_step_bound.py`'s own
raw count) — the third collision this phase on the same fact. `tests/test_proposal_tools.py`
keeps the one canonical COUNT pin (`test_the_four_proposal_tools_are_registered_with_descriptions`,
`assert len(by_name) == 14`); this module is the one place the NAME list itself lives, so a 15th
tool touches this file (plus whatever test specifically exercises the new tool), not three.

Not a test module itself — the leading underscore keeps pytest from collecting it, the same
convention `tests/auth_helpers.py`/`tests/oauth_helpers.py` already use for shared test fixtures.
"""

from __future__ import annotations

MCP_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "search_content",
        "count_content",
        "create_draft",
        "edit_content",
        "delete_content",
        "tag_content",
        "publish",
        "archive",
        "report_content_gaps",
        "report_weak_queries",
        "propose_content_fix",
        "list_proposals",
        "accept_proposal",
        "reject_proposal",
    }
)
