"""知识百科批量生成任务：把耗时的模型生成移到后台并持久化进度。

前端切换页面后组件会销毁；任务状态必须落库，回来时才能继续显示
「生成中 X/Y」而不是一个已经消失的 loading。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import RagWikiBuildJob
from app.services.rag.wiki_service import build_wiki_pages


def _job_dict(job: RagWikiBuildJob) -> Dict[str, Any]:
    return {
        "jobId": int(job.id),
        "kbId": int(job.kb_id),
        "status": job.status,
        "total": int(job.total or 0),
        "done": int(job.done or 0),
        "failed": int(job.failed or 0),
        "currentTitle": job.current_title or "",
        "error": job.error or "",
        "active": job.status == "running",
        "createTime": job.create_time.strftime("%Y-%m-%d %H:%M:%S") if job.create_time else "",
        "finishedAt": job.finished_at.strftime("%Y-%m-%d %H:%M:%S") if job.finished_at else "",
    }


async def create_build_job(
    db: AsyncSession,
    user_id: int,
    kb_id: int,
    *,
    force: bool,
    limit: int,
) -> tuple[Dict[str, Any], bool]:
    """创建或复用当前资料夹的生成任务。"""
    active = (
        await db.execute(
            select(RagWikiBuildJob)
            .where(
                RagWikiBuildJob.user_id == int(user_id),
                RagWikiBuildJob.kb_id == int(kb_id),
                RagWikiBuildJob.status == "running",
            )
            .order_by(RagWikiBuildJob.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if active is not None:
        return _job_dict(active), False
    job = RagWikiBuildJob(
        user_id=int(user_id),
        kb_id=int(kb_id),
        status="running",
        total=max(1, int(limit)),
        done=0,
        failed=0,
        update_time=datetime.now(),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return _job_dict(job), True


async def _update_job(
    job_id: int,
    *,
    done: int,
    total: int,
    failed: int,
    current_title: str,
    status: Optional[str] = None,
    error: str = "",
) -> None:
    from app.database import async_session_factory

    async with async_session_factory() as db:
        job = await db.get(RagWikiBuildJob, int(job_id))
        if job is None:
            return
        job.done = int(done)
        job.total = max(1, int(total))
        job.failed = int(failed)
        job.current_title = str(current_title or "")[:255]
        job.error = str(error or "")[:480]
        job.update_time = datetime.now()
        if status:
            job.status = status
            if status != "running":
                job.finished_at = datetime.now()
        await db.commit()


async def run_build_job(
    job_id: int,
    user_id: int,
    kb_id: int,
    *,
    force: bool,
    limit: int,
) -> None:
    """后台执行知识百科生成，逐个主题回写进度。"""
    from app.database import async_session_factory

    async with async_session_factory() as db:
        try:
            async def progress(done: int, total: int, failed: int, title: str) -> None:
                await _update_job(
                    job_id,
                    done=done,
                    total=total,
                    failed=failed,
                    current_title=title,
                )

            result = await build_wiki_pages(
                db,
                int(user_id),
                int(kb_id),
                force=bool(force),
                limit=int(limit),
                progress_cb=progress,
            )
            done = int(result.get("processed") or 0)
            failed = len(result.get("errors") or [])
            await _update_job(
                job_id,
                done=done,
                total=max(1, done + failed),
                failed=failed,
                current_title="",
                status="done",
            )
        except Exception as exc:  # noqa: BLE001
            await _update_job(
                job_id,
                done=0,
                total=max(1, int(limit)),
                failed=0,
                current_title="",
                status="failed",
                error=str(exc)[:480],
            )


async def get_build_job(
    db: AsyncSession, user_id: int, job_id: int
) -> Dict[str, Any]:
    job = (
        await db.execute(
            select(RagWikiBuildJob).where(
                RagWikiBuildJob.id == int(job_id),
                RagWikiBuildJob.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise ValueError("知识百科任务不存在或无权访问")
    return _job_dict(job)


async def get_latest_build_job(
    db: AsyncSession, user_id: int, kb_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    query = select(RagWikiBuildJob).where(RagWikiBuildJob.user_id == int(user_id))
    if kb_id is not None:
        query = query.where(RagWikiBuildJob.kb_id == int(kb_id))
    job = (
        await db.execute(query.order_by(RagWikiBuildJob.id.desc()).limit(1))
    ).scalar_one_or_none()
    return _job_dict(job) if job else None


__all__ = [
    "create_build_job",
    "run_build_job",
    "get_build_job",
    "get_latest_build_job",
]
