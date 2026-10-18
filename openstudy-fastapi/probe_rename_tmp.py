# -*- coding: utf-8 -*-
"""把会话标题改掉（不动消息）。"""
import asyncio, sys
sys.stdout.reconfigure(encoding="utf-8")
from sqlalchemy import text
from app.database import async_session_factory

async def main():
    async with async_session_factory() as db:
        r = await db.execute(text("select session_id, title, (select count(*) from ai_chat_message m where m.session_id=s.session_id) from ai_chat_session s where session_id=:s"), {"s": "diag-live2"})
        print("before:", r.fetchall())
        await db.execute(text("update ai_chat_session set title=:t where session_id=:s"),
                         {"t": "AI 智能体全链路联调（长会话）", "s": "diag-live2"})
        await db.commit()
        r2 = await db.execute(text("select session_id, title from ai_chat_session where session_id=:s"), {"s": "diag-live2"})
        print("after:", r2.fetchall())

asyncio.run(main())
