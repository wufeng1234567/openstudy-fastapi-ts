import asyncio
import json
from app.database import async_session
from app.models.notice import SysNotice
from sqlalchemy import select

async def check():
    async with async_session() as db:
        result = await db.execute(
            select(SysNotice).where(SysNotice.status == "0").order_by(SysNotice.create_time.desc())
        )
        notices = list(result.scalars().all())
        
        for notice in notices:
            print(f"\nnotice_id: {notice.notice_id}")
            print(f"  title: {notice.notice_title}")
            print(f"  remark: {repr(notice.remark)}")
            print(f"  remark type: {type(notice.remark)}")
            print(f"  remark is None: {notice.remark is None}")
            print(f"  bool(remark): {bool(notice.remark)}")
            
            # Simulate the backend code
            remark = notice.remark or ""
            print(f"  after 'or \"\"': {repr(remark)}")
            
            if remark:
                import json
                remark_obj = json.loads(remark)
                print(f"  parsed remark: {remark_obj}")

asyncio.run(check())
