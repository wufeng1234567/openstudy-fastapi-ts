"""Small pagination helper shared by API modules.

Historically each list endpoint repeated:

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    query = query.offset((page_num - 1) * page_size).limit(page_size)

This helper keeps the exact same SQL semantics while making the page bounds and
total count consistent across modules.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def paginate(
    db: AsyncSession,
    query: Select[Any],
    *,
    page_num: int = 1,
    page_size: int = 10,
    order_by: Optional[Any] = None,
) -> tuple[int, Sequence[Any]]:
    """Return ``(total, rows)`` for a SELECT query.

    ``page_num`` is 1-based; values below 1 are clamped to 1.  ``page_size`` is
    clamped to 1..1000 so a malformed query cannot ask the database for an
    unbounded result set.
    """
    page = max(1, int(page_num or 1))
    size = max(1, min(int(page_size or 10), 1000))

    total = int(await db.scalar(select(func.count()).select_from(query.subquery())) or 0)

    paged_query = query
    if order_by is not None:
        if isinstance(order_by, (tuple, list)):
            paged_query = paged_query.order_by(*order_by)
        else:
            paged_query = paged_query.order_by(order_by)
    paged_query = paged_query.offset((page - 1) * size).limit(size)
    result = await db.execute(paged_query)
    return total, list(result.scalars().all())


def select_count(query: Select[Any]) -> Select[Any]:
    """Build the canonical ``select count(*) from (subquery)`` query."""
    return select(func.count()).select_from(query.subquery())


__all__ = ["paginate", "select_count"]
