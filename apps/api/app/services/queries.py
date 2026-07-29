"""THE §4.1 active-row filter — every read of `users`/`content`/`tags` goes through it.

CONVENTIONS.md §3: soft-delete filtering is defined once here; an ad-hoc
`.where(Model.is_deleted == False)` anywhere else in the codebase is a
review-blocking defect (PRD §4.1) — a missed filter is a data leak.
"""

from __future__ import annotations

from typing import TypeVar

from sqlalchemy import Select, select

from app.models.base import SoftDeleteMixin

ModelT = TypeVar("ModelT", bound=SoftDeleteMixin)


def active_select(model: type[ModelT]) -> Select[tuple[ModelT]]:
    """Return a `Select` for `model` restricted to non-deleted rows.

    PRD §4.1: the define-once active-row filter. Every later read of a
    soft-deletable model (`User`, `Content`, `Tag`) must build on this
    helper rather than repeating the `is_deleted` condition ad hoc.

    Args:
        model: a soft-deletable ORM model class (mixes in `SoftDeleteMixin`).

    Returns:
        A `Select` selecting `model` rows where `is_deleted` is false.
    """
    return select(model).where(model.is_deleted.is_(False))
