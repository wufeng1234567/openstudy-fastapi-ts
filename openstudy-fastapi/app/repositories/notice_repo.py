"""
通知公告仓库
"""

from typing import Optional, Tuple, List
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.notice import SysNotice


class NoticeRepository:
    """通知公告仓库"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_notices(
        self,
        notice_title: Optional[str] = None,
        notice_type: Optional[str] = None,
        status: Optional[str] = None,
        page_num: int = 1,
        page_size: int = 10,
    ) -> Tuple[int, List[SysNotice]]:
        """查询公告列表"""
        query = select(SysNotice)

        if notice_title:
            query = query.where(SysNotice.notice_title.ilike(f"%{notice_title}%"))
        if notice_type:
            query = query.where(SysNotice.notice_type == notice_type)
        if status:
            query = query.where(SysNotice.status == status)

        # 计算总数
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        # 分页
        query = query.order_by(SysNotice.create_time.desc())
        query = query.offset((page_num - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        return total, list(result.scalars().all())

    async def get_by_id(self, notice_id: int) -> Optional[SysNotice]:
        """根据ID查询公告"""
        query = select(SysNotice).where(SysNotice.notice_id == notice_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create(self, notice: SysNotice) -> SysNotice:
        """创建公告"""
        self.db.add(notice)
        await self.db.flush()
        await self.db.refresh(notice)
        return notice

    async def update(self, notice: SysNotice) -> None:
        """更新公告"""
        await self.db.merge(notice)

    async def delete_by_ids(self, ids: List[int]) -> None:
        """删除公告"""
        stmt = SysNotice.__table__.delete().where(SysNotice.notice_id.in_(ids))
        await self.db.execute(stmt)
