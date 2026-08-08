"""SSE wire utilities: format one `event:`/`data:` block, wrap a generator in a streaming
response (PRD §5.3, §5.4).

`POST /public/chat` (phase-4 task-02, this task) and `POST /agent/chat` (phase-5) share this
exact wire format — both are expected to reuse `sse_event`/`sse_response` verbatim rather than
each reimplementing SSE framing.

Phase-6 task-01: `sse_response` grew one optional parameter, `on_first_event` — a hook the
phase-6 latency-metrics middleware uses to time `/public/chat`'s first-token latency (PRD §9.1)
without this module knowing anything about SSE event *names* or latency metrics itself (task
brief: "wrap, don't modify event semantics"). Every event's bytes on the wire are unchanged either
way; `on_first_event=None` (every pre-phase-6 caller, and every phase-4/phase-5 test) means the
hook simply never fires.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping

from fastapi.responses import StreamingResponse


def sse_event(name: str, payload: Mapping[str, object]) -> str:
    """Format one SSE event block: `event: <name>\\ndata: <json>\\n\\n`.

    `payload` is JSON-encoded with `json.dumps`'s own default (compact, single-line, no
    whitespace) — callers must pass already-JSON-safe values (`str`/`int`/`float`/`bool`/`None`/
    `list`/`dict`; a `uuid.UUID` must already be `str()`-ed before it reaches this function, since
    `json.dumps` cannot encode one).

    Args:
        name: the SSE event name (`token`, `citations`, `done`, `error`, ...).
        payload: the JSON-serializable payload for this event's `data:` line.

    Returns:
        The formatted, blank-line-terminated SSE block.
    """
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n"


def sse_response(
    generator: Iterator[str], on_first_event: Callable[[], None] | None = None
) -> StreamingResponse:
    """Wrap `generator` (already-formatted `sse_event(...)` strings) in a `text/event-stream`
    `StreamingResponse` with no-cache headers, so no intermediary buffers or caches the stream.

    Args:
        generator: an iterator yielding already-formatted SSE blocks (`sse_event`'s output), in
            the order they should reach the client.
        on_first_event: an optional zero-argument callback invoked exactly once, immediately
            before the FIRST item leaves `generator` (module docstring, phase-6 task-01) — every
            item's bytes on the wire, including the first, are completely unchanged either way.
            `None` (the default) means the hook never fires. `public_routes.public_chat` is the
            one caller that passes one, to time and record `/public/chat`'s first-token latency.

    Returns:
        A `StreamingResponse` ready to return directly from a route.
    """
    body = (
        generator if on_first_event is None else _call_before_first_item(generator, on_first_event)
    )
    return StreamingResponse(
        body,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _call_before_first_item(
    generator: Iterator[str], on_first_event: Callable[[], None]
) -> Iterator[str]:
    """Call `on_first_event()` once, right before the first item leaves `generator` — every item
    (including the first) passes through byte-for-byte unchanged after that. Never fires at all
    if `generator` yields nothing (e.g. an exchange that fails before any event is produced).
    """
    is_first = True
    for item in generator:
        if is_first:
            on_first_event()
            is_first = False
        yield item
