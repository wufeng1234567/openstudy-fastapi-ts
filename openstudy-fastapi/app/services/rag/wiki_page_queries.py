"""Wiki 主题页的**取数**辅助（从 `wiki_service.py` 抽出）。

  · `load_page` —— 按 id + user 取一个主题页（取不到返回 None）

⚠ 依赖方向单向：`wiki_service.py` → 本模块；本模块**不反向依赖**它
   （`wiki_payload_helpers` 无项目级回引），因此不会形成循环依赖。

⚠ **落库 / 检索 / LLM 流程与响应形状一个字节都没动** —— 这里只是把
   「页面怎么取」收敛到一处；取不到页面时的报错文案、调用顺序、返回的 dict 形状
   全部原样保留在 `wiki_service.py` 里。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wiki import RagWikiPage


async def load_page(
    db: AsyncSession, user_id: int, page_id: int
) -> Optional[RagWikiPage]:
    """按 id + user 取一个主题页（取不到返回 `None`）。

    ⚠️ 这段查询原本在**六处**逐字相同（详情 / 改页面 / 增删内链 / 恢复版本…）——
    现在收敛到一处，「按 id + user 双重校验」的取数口径不会再各处漂。
    """
    return (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.id == int(page_id),
                RagWikiPage.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
