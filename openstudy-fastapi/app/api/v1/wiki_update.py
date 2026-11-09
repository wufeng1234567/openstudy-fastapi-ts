"""知识百科按来源增量更新。

不修改基线 `rag.py` / `wiki.py`：这里只增加一个入口，把用户选中的一个
文档/图片/网页先标成 stale，再复用现有知识百科构建任务；已有 ready 页
在 `force=False` 下不会被重新生成。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error, success
from app.core.security import get_current_user
from app.database import get_db
from app.models.wiki import RagWikiPage
from app.services import source_graph_state_service
from app.services.rag import source_graph_service

router = APIRouter(prefix="/rag")


def _uid(current_user: dict) -> int:
    return int(current_user.get("userId") or current_user.get("user_id") or 0)


class WikiSelectiveBuildRequest(BaseModel):
    kbId: int = 0
    sourceType: str = "document"
    sourceId: int = 0
    limit: int = 120


class WikiIncrementalBuildRequest(BaseModel):
    kbId: int = 0
    limit: int = 30


async def _run_incremental_sources(job_id: int, user_id: int, kb_id: int, states: list, limit: int) -> None:
    """后台按来源执行增量更新；每个来源独立 session，失败不拖垮其他来源。"""
    from app.database import async_session_factory
    from app.services.rag.wiki_build_job_service import _update_job
    from app.services.rag.wiki_service import build_wiki_pages

    total = max(1, len(states))
    failed = 0
    done = 0
    lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(3)

    async def process(state: dict) -> None:
        nonlocal failed, done
        source_type = str(state.get("sourceType") or "")
        source_id = int(state.get("sourceId") or 0)
        source_name = str(state.get("sourceName") or "来源")
        ok = True
        try:
            async with semaphore:
                async with async_session_factory() as db:
                    if source_type in {"document", "web"}:
                        await build_wiki_pages(
                            db,
                            int(user_id),
                            int(kb_id),
                            force=False,
                            limit=max(1, min(int(limit or 30), 30)),
                            doc_ids=[source_id],
                        )
                    elif source_type == "bank":
                        await source_graph_service.sync_bank_graph(
                            db,
                            user_id=int(user_id),
                            kb_id=int(kb_id),
                            bank_id=source_id,
                            source_name=source_name,
                        )
                    elif source_type in {"image", "note"}:
                        text = await source_graph_state_service.source_text(
                            db, source_type=source_type, source_id=source_id
                        )
                        if not text.strip():
                            raise ValueError("来源没有可抽取的文本")
                        await source_graph_service.sync_text_source(
                            db,
                            user_id=int(user_id),
                            kb_id=int(kb_id),
                            source_type=source_type,
                            source_id=source_id,
                            source_name=source_name,
                            text=text,
                        )
                    await source_graph_state_service.mark_state(
                        db, state_id=int(state["stateId"]), status="done"
                    )
                    await db.commit()
        except Exception as exc:  # noqa: BLE001
            ok = False
            try:
                async with async_session_factory() as db:
                    await source_graph_state_service.mark_state(
                        db,
                        state_id=int(state["stateId"]),
                        status="failed",
                        error=str(exc)[:480],
                    )
                    await db.commit()
            except Exception:
                pass
        async with lock:
            done += 1
            if not ok:
                failed += 1
            await _update_job(
                job_id,
                done=done,
                total=total,
                failed=failed,
                current_title=source_name,
                status="running" if done < len(states) else "done",
            )

    await asyncio.gather(*(process(state) for state in states))


async def _mark_source_pages_stale(db: AsyncSession, *, user_id: int, kb_id: int, source_id: int) -> int:
    pages = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.kb_id == int(kb_id),
            )
        )
    ).scalars().all()
    touched = 0
    for page in pages:
        if str(page.generated_by or "") in {"manual", "agent"}:
            continue
        doc_ids = [int(item) for item in (page.source_doc_ids or []) if str(item).isdigit()]
        if int(source_id) in doc_ids:
            page.status = "stale"
            touched += 1
    if touched:
        await db.commit()
    return touched


@router.post("/wiki/build/incremental")
async def build_wiki_incremental(
    data: WikiIncrementalBuildRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """只处理未处理或内容变化的来源；已处理来源不会重新交给 LLM。"""
    try:
        pending = await source_graph_state_service.sync_states(
            db,
            user_id=_uid(current_user),
            kb_id=int(data.kbId or 0),
        )
        await db.commit()
        if not pending:
            return success(
                {"jobId": 0, "status": "done", "total": 0, "done": 0, "failed": 0, "skipped": True},
                "没有需要更新的来源",
            )

        from app.services.rag.wiki_build_job_service import create_build_job

        limit = max(1, min(int(data.limit or 30), 30))
        job, created = await create_build_job(
            db,
            _uid(current_user),
            int(data.kbId or 0),
            force=False,
            limit=len(pending),
        )
        if created:
            background_tasks.add_task(
                _run_incremental_sources,
                job["jobId"],
                _uid(current_user),
                int(data.kbId or 0),
                pending,
                limit,
            )
        return success(job, "已开始按来源增量更新" if created else "知识百科任务进行中")
    except Exception as exc:  # noqa: BLE001
        return error(f"增量更新失败：{exc}")


@router.post("/wiki/build/selective")
async def build_wiki_selective(
    data: WikiSelectiveBuildRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    source_type = str(data.sourceType or "").strip().lower()
    if source_type not in {"document", "image", "bank", "web"}:
        return error("sourceType 只支持 document / image / bank / web")
    if source_type == "bank":
        # 题库没有 wiki 页；按题目块抽取知识点/实体关系，供知识图谱使用。
        from app.services.rag import source_graph_service

        if int(data.sourceId or 0) <= 0:
            return error("请选择一个具体题库")
        try:
            stats = await source_graph_service.sync_bank_graph(
                db,
                user_id=_uid(current_user),
                kb_id=int(data.kbId or 0),
                bank_id=int(data.sourceId),
                source_name="题库",
            )
            return success(
                {
                    "mode": "bank",
                    "bankId": int(data.sourceId),
                    "summary": "题库知识点已写入知识图谱和知识百科",
                    "entities": [],
                    "relations": [],
                    "stats": stats,
                },
                f"题库知识点已同步：{stats.get('entities', 0)} 个知识点、{stats.get('pages', 0)} 个主题页",
            )
        except Exception as exc:  # noqa: BLE001
            return error(f"题库知识点抽取失败：{exc}")
    if int(data.sourceId or 0) <= 0:
        return error("请选择一个具体来源")
    try:
        touched = await _mark_source_pages_stale(
            db,
            user_id=_uid(current_user),
            kb_id=int(data.kbId or 0),
            source_id=int(data.sourceId),
        )
        from app.services.rag.wiki_build_job_service import create_build_job, run_build_job

        # force=False：只更新 stale 页面，已有 ready 页面保持不动。
        job, created = await create_build_job(
            db,
            _uid(current_user),
            int(data.kbId or 0),
            force=False,
            limit=max(1, min(int(data.limit or 120), 500)),
        )
        if created:
            background_tasks.add_task(
                run_build_job,
                job["jobId"],
                _uid(current_user),
                int(data.kbId or 0),
                force=False,
                limit=max(1, min(int(data.limit or 120), 500)),
            )
        job["stalePages"] = touched
        return success(job, "已开始增量更新" if created else "知识百科任务进行中")
    except Exception as exc:  # noqa: BLE001
        return error(f"按来源更新知识百科失败：{exc}")
