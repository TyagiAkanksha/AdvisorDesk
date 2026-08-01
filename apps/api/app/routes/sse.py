"""SSE wire utilities: format one `event:`/`data:` block, wrap a generator in a streaming
response (PRD §5.3, §5.4).

`POST /public/chat` (phase-4 task-02, this task) and `POST /agent/chat` (phase-5) share this
exact wire format — both are expected to reuse `sse_event`/`sse_response` verbatim rather than
each reimplementing SSE framing.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping

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


def sse_response(generator: Iterator[str]) -> StreamingResponse:
    """Wrap `generator` (already-formatted `sse_event(...)` strings) in a `text/event-stream`
    `StreamingResponse` with no-cache headers, so no intermediary buffers or caches the stream.

    Args:
        generator: an iterator yielding already-formatted SSE blocks (`sse_event`'s output), in
            the order they should reach the client.

    Returns:
        A `StreamingResponse` ready to return directly from a route.
    """
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
