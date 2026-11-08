"""知识百科按来源增量更新。

不修改基线 `rag.py` / `wiki.py`：这里只增加一个入口，把用户选中的一个
文档/图片/网页先标成 stale，再复用现有知识百科构建任务；已有 ready 页
在 `force=False` 下不会被重新生成。
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error, success
from app.core.security import get_current_user
from app.database import get_db
from app.models.wiki import RagWikiPage

router = APIRouter(prefix="/rag")


def _uid(current_user: dict) -> int:
    return int(current_user.get("userId") or current_user.get("user_id") or 0)


class WikiSelectiveBuildRequest(BaseModel):
    kbId: int = 0
    sourceType: str = "document"
    sourceId: int = 0
    limit: int = 120


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
        from app.services import source_entity_service

        if int(data.sourceId or 0) <= 0:
            return error("请选择一个具体题库")
        try:
            result = await source_entity_service.extract_bank_entities(
                db,
                user_id=_uid(current_user),
                bank_id=int(data.sourceId),
                limit=200,
                chunk_size=20,
                use_llm=True,
            )
            return success(
                {
                    "mode": "bank",
                    "bankId": int(data.sourceId),
                    "entities": result.get("entities") or [],
                    "relations": result.get("relations") or [],
                    "degraded": result.get("degraded") or {},
                },
                f"题库知识点已抽取：{len(result.get('entities') or [])} 个知识点",
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
