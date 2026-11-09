"""启动时回收上一次进程异常退出后遗留的 AI 后台任务。

图片描述任务和知识百科构建任务都是「进程内 BackgroundTask」，进程重启后
不会自动恢复。如果不清理，数据库里会永远保留 `running`，前端刷新后就会
一直显示「正在生成图片描述」或「正在更新知识百科」。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import update

from app.database import async_session_factory
from app.models.content import RagImageDescribeJob, RagWikiBuildJob


async def recover_stale_ai_jobs() -> dict:
    now = datetime.now()
    total = {"imageDescribe": 0, "wikiBuild": 0}
    async with async_session_factory() as db:
        image_result = await db.execute(
            update(RagImageDescribeJob)
            .where(RagImageDescribeJob.status == "running")
            .values(
                status="failed",
                error="服务重启，图片描述任务已中断，请重新发起",
                update_time=now,
                finished_at=now,
            )
        )
        total["imageDescribe"] = int(image_result.rowcount or 0)

        wiki_result = await db.execute(
            update(RagWikiBuildJob)
            .where(RagWikiBuildJob.status == "running")
            .values(
                status="failed",
                error="服务重启，知识百科更新任务已中断，请重新发起",
                update_time=now,
                finished_at=now,
            )
        )
        total["wikiBuild"] = int(wiki_result.rowcount or 0)
        await db.commit()
    return total


__all__ = ["recover_stale_ai_jobs"]
