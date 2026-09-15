import asyncio
from app.database import async_session
from app.models.notice import SysNotice
from sqlalchemy import select

async def check():
    async with async_session() as db:
        result = await db.execute(select(SysNotice).where(SysNotice.notice_id == 34))
        notice = result.scalar_one()
        print("notice_id:", notice.notice_id)
        print("remark:", repr(notice.remark))

asyncio.run(check())
