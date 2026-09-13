"""Write tools: `create_draft`/`edit_content`/`delete_content`/`tag_content`/`publish`/
`archive` — wrap the content/tag services (PRD §6, phase-5 task-02).

Every handler is a thin wrapper — parse (the Pydantic args model) -> call one
`app.services.content`/`app.services.tags` function -> build the returned dict — exactly
`tools_read.py`'s own registration pattern (one `ToolSpec` per tool, a Pydantic args model
paired with a `(args, *, session, actor_id) -> dict` handler). No business logic lives here;
lifecycle rules (re-chunk-iff-published, the publish/archive transition matrix, soft-delete
tombstoning, tag reactivation) all live in the wrapped service functions, most of them
task-00-hardened already.

PIPELINE THREADING (this task's judgment call, disclosed in the implementer report): five of
these six tools wrap a service function that takes a REQUIRED `pipeline: ChunkPipeline`
keyword argument (`update_content`, `delete_content`, `publish_content`, `archive_content`;
`create_draft`/`update_content_tags` need none). `app.mcp.runtime.call_tool` grew a new
optional `pipeline` keyword-only parameter for exactly this (see that module's docstring),
but the handler-call shape `spec.handler(args, session=session, actor_id=actor_id)` is pinned
by `tests/test_mcp_runtime_guards.py`/`tests/test_mcp_read_tools.py` and could not grow a
fourth argument. `call_tool` instead stashes the resolved pipeline on
`session.info[SESSION_INFO_PIPELINE_KEY]` right before calling any handler (every tool call,
not just a write one — harmless for the two read tools, which never look at it); handlers
below that need it read it back via `app.mcp.tool_spec.pipeline_from_session`.

FAIL LOUD, NOT SILENT (fix round 1, finding I1): `call_tool` itself still defaults its own
`pipeline` parameter to `NoopChunkPipeline()` when a caller passes none — that default is
correct and stays (read-tool ergonomics, and every pinned test that never bothers to pass a
pipeline for a write tool it doesn't care about). But `app.mcp.tool_spec.pipeline_from_session`
is a different seam: it asserts that `call_tool`'s stash actually happened. If a write handler is
ever reached WITHOUT going through `call_tool` (a future direct
`WRITE_TOOLS[i].handler(...)` call, a second `call_tool`-like entry point, a refactor that
moves the stash below the handler invocation), silently substituting a `NoopChunkPipeline()`
here would let e.g. `publish` commit a `status='published'` row with zero chunks — invisible
to retrieval forever, no exception, no failing test (PRD §4: "partial chunk sets must never
be visible to retrieval"). This mirrors `app.routes.deps.get_session`/`get_chat_llm`/
`get_embedder`'s own philosophy for an unresolvable injected seam: fail loudly, never
silently degrade.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.mcp.tool_spec import ToolSpec, pipeline_from_session
from app.services import content as content_service
from app.services.tags import tags_for_contents

# ---------------------------------------------------------------------------
# create_draft
# ---------------------------------------------------------------------------


class CreateDraftArgs(BaseModel):
    """`create_draft`'s arguments (PRD §6): `title`, `body_md`, `tags`.

    `title`'s validation mirrors `app.models.schemas.content.ContentCreate.title` exactly
    (`min_length=1` plus the same whitespace-only rejection) — the Goal's "same behavior as
    the REST routes by construction" extends to input validation, not just the service calls.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    body_md: str = ""
    # Final-review fix (F5, t02 M3): `json_schema_extra` puts an explicit `"default": []` into
    # the exported `mcp-tools.json` — Pydantic's `default_factory` alone leaves the property with
    # no visible default in the JSON Schema (still correctly non-`required`, but silent on WHAT
    # omitting it means). The checkpoint's own probe found the model struggles with exactly this
    # kind of unstated-default list argument; the schema is the model's only view of the
    # contract, so the default belongs in it, not just in this class's runtime behavior.
    tags: list[str] = Field(default_factory=list, json_schema_extra={"default": []})

    @field_validator("title")
    @classmethod
    def _title_not_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be empty or whitespace-only")
        return value


def _create_draft(
    args: CreateDraftArgs, *, session: Session, actor_id: uuid.UUID
) -> dict[str, Any]:
    """`{id, slug}` (PRD §6): always `status='draft'`; actor stamped as `author_id`/`updated_by`."""
    content = content_service.create_draft(
        session, title=args.title, body_md=args.body_md, tags=args.tags, actor_id=actor_id
    )
    return {"id": str(content.id), "slug": content.slug}


# ---------------------------------------------------------------------------
# edit_content
# ---------------------------------------------------------------------------


class EditContentArgs(BaseModel):
    """`edit_content`'s arguments (PRD §6): partial update — every field but `content_id`
    optional, mirroring `app.models.schemas.content.ContentUpdate`'s own `None`-means-
    unchanged contract and title validation."""

    model_config = ConfigDict(extra="forbid")

    content_id: uuid.UUID
    title: str | None = Field(default=None, min_length=1)
    body_md: str | None = None
    tags: list[str] | None = None

    @field_validator("title")
    @classmethod
    def _title_not_whitespace_only(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("title must not be empty or whitespace-only")
        return value


def _edit_content(
    args: EditContentArgs, *, session: Session, actor_id: uuid.UUID
) -> dict[str, Any]:
    """`{id, slug, status}` (PRD §6): re-embeds iff published; slug never changes."""
    content = content_service.update_content(
        session,
        args.content_id,
        title=args.title,
        body_md=args.body_md,
        tags=args.tags,
        actor_id=actor_id,
        pipeline=pipeline_from_session(session),
    )
    return {"id": str(content.id), "slug": content.slug, "status": content.status}


# ---------------------------------------------------------------------------
# delete_content / publish / archive share one `content_id`-only args model
# ---------------------------------------------------------------------------


# Final-review fix (F5, t02 M6): this class's docstring becomes `inputSchema.description` on
# EVERY tool that uses it (`delete_content`, `publish`, `archive`) — it previously named all
# three sibling tools by name, so e.g. `publish`'s own exported schema told the model about
# `delete_content` and `archive` too, information irrelevant (and mildly confusing) to a model
# looking only at `publish`'s schema. Kept neutral below on purpose: say what the field IS, not
# which other tools happen to share its shape.
class ContentIdArgs(BaseModel):
    """A single `content_id` argument (PRD §6) — no other fields."""

    model_config = ConfigDict(extra="forbid")

    content_id: uuid.UUID


def _delete_content(
    args: ContentIdArgs, *, session: Session, actor_id: uuid.UUID
) -> dict[str, Any]:
    """`{deleted: true}` (PRD §6): soft-delete tombstone + chunk removal in one transaction."""
    content_service.delete_content(
        session, args.content_id, actor_id=actor_id, pipeline=pipeline_from_session(session)
    )
    return {"deleted": True}


def _publish(args: ContentIdArgs, *, session: Session, actor_id: uuid.UUID) -> dict[str, Any]:
    """`{id, status, published_at}` (PRD §6): the full §4 publish transaction.

    `published_at` is returned as an ISO-8601 string, not a raw `datetime` — the HTTP
    transport (`app.mcp.server._execute_tool_call`) `json.dumps`s this dict directly, which
    cannot serialize a `datetime` on its own.
    """
    content = content_service.publish_content(
        session, args.content_id, actor_id=actor_id, pipeline=pipeline_from_session(session)
    )
    return {
        "id": str(content.id),
        "status": content.status,
        "published_at": content.published_at.isoformat() if content.published_at else None,
    }


def _archive(args: ContentIdArgs, *, session: Session, actor_id: uuid.UUID) -> dict[str, Any]:
    """`{id, status}` (PRD §6): status -> archived, chunks removed."""
    content = content_service.archive_content(
        session, args.content_id, actor_id=actor_id, pipeline=pipeline_from_session(session)
    )
    return {"id": str(content.id), "status": content.status}


# ---------------------------------------------------------------------------
# tag_content
# ---------------------------------------------------------------------------


class TagContentArgs(BaseModel):
    """`tag_content`'s arguments (PRD §6): `content_id`, plus `add`/`remove` name lists."""

    model_config = ConfigDict(extra="forbid")

    content_id: uuid.UUID
    # Final-review fix (F5, t02 M3) — see `CreateDraftArgs.tags`'s comment for the full reasoning.
    add: list[str] = Field(default_factory=list, json_schema_extra={"default": []})
    remove: list[str] = Field(default_factory=list, json_schema_extra={"default": []})


def _tag_content(args: TagContentArgs, *, session: Session, actor_id: uuid.UUID) -> dict[str, Any]:
    """`{id, tags}` (PRD §6): `add`/`remove` applied together via `update_content_tags`.

    `tags` is read back through `tags_for_contents` (the same batch tag-lookup the read tools
    and REST routes use) rather than re-deriving it from `update_content_tags`'s return value
    — one canonical way to turn a `Content.id` into its current tag names.
    """
    content = content_service.update_content_tags(
        session, args.content_id, add=args.add, remove=args.remove, actor_id=actor_id
    )
    tags = tags_for_contents(session, [content.id])[content.id]
    return {"id": str(content.id), "tags": tags}


WRITE_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="create_draft",
        description=(
            "Create a draft CMS content item. Creates missing tags (reactivating "
            "soft-deleted names). Always returns status 'draft' — never auto-published."
        ),
        args_model=CreateDraftArgs,
        handler=_create_draft,
    ),
    ToolSpec(
        name="edit_content",
        description=(
            "Partially update a content item's title/body/tags. Re-embeds if the item is "
            "already published. The slug never changes."
        ),
        args_model=EditContentArgs,
        handler=_edit_content,
    ),
    ToolSpec(
        name="delete_content",
        description=(
            "Soft-delete a content item (tombstone, not restorable) and remove its chunks "
            "in one transaction."
        ),
        args_model=ContentIdArgs,
        handler=_delete_content,
    ),
    ToolSpec(
        name="tag_content",
        description=(
            "Add and/or remove tags on a content item in one call. Tags in `add` are "
            "created if missing (reactivating soft-deleted names)."
        ),
        args_model=TagContentArgs,
        handler=_tag_content,
    ),
    ToolSpec(
        name="publish",
        description="Publish a content item: runs the full publish transaction (§4).",
        args_model=ContentIdArgs,
        handler=_publish,
    ),
    ToolSpec(
        name="archive",
        description="Archive a content item: status -> archived, removes its chunks.",
        args_model=ContentIdArgs,
        handler=_archive,
    ),
)
