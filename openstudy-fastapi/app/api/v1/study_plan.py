"""规划建议工作台 API：统一图谱 / trace / advice / 历史快照。

放在新文件里，避免改 `rag.py` 基线；main.py 中必须排在 rag.router 之前，
否则 `/rag/*` 的兜底路由可能截走这些端点。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error, success
from app.core.security import get_current_user
from app.database import get_db
from app.services import source_entity_service, study_advice_export_service, study_advice_service, study_plan_history_service
from app.services.rag import study_map_service

router = APIRouter(prefix="/rag")


def _uid(current_user: dict) -> int:
    return int(current_user.get("userId") or current_user.get("user_id") or 0)


def _parse_ids(value: str = "") -> List[int]:
    result: List[int] = []
    for item in str(value or "").split(","):
        item = item.strip()
        if item:
            try:
                result.append(int(item))
            except ValueError:
                continue
    return result


class StudyMapQuery(BaseModel):
    pass


class TraceRequest(BaseModel):
    kbId: int = 0
    bankIds: List[int] = Field(default_factory=list)
    sourceTypes: List[str] = Field(default_factory=lambda: ["wiki", "bank"])
    seedNodeId: str = ""
    goal: str = "weakness"
    dailyMinutes: int = 30
    horizonDays: int = 14
    instruction: str = ""


class AdviceRequest(TraceRequest):
    traceId: str = ""
    parentSnapshotId: int = 0
    save: bool = True
    useLlm: bool = True


class HistorySaveRequest(BaseModel):
    kbId: int = 0
    title: str = ""
    scope: Dict[str, Any] = Field(default_factory=dict)
    advice: Dict[str, Any] = Field(default_factory=dict)
    trace: Dict[str, Any] = Field(default_factory=dict)
    graph: Dict[str, Any] = Field(default_factory=dict)
    parentId: int = 0
    source: str = "page"


class HistoryPatchRequest(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None


class SourceEntityRequest(BaseModel):
    sourceType: str = "bank"
    sourceId: int = 0
    limit: int = 20
    useLlm: bool = True


class AdviceExportRequest(BaseModel):
    format: str = "pdf"
    advice: Dict[str, Any] = Field(default_factory=dict)


@router.post("/study-source-entities")
async def extract_study_source_entities(
    data: SourceEntityRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """从题库内容抽取知识点/实体/关系；不把题干当作图节点。"""
    try:
        if data.sourceType != "bank" or int(data.sourceId or 0) <= 0:
            return error("目前只支持从题库抽取知识点，请传 sourceType=bank 和 sourceId")
        result = await source_entity_service.extract_bank_entities(
            db,
            user_id=_uid(current_user),
            bank_id=int(data.sourceId),
            limit=data.limit,
            use_llm=bool(data.useLlm),
        )
        return success(result)
    except Exception as exc:  # noqa: BLE001
        return error(f"抽取来源知识点失败：{exc}")


@router.get("/study-map")
async def get_study_map(
    kbId: int = Query(0, ge=0),
    bankIds: str = Query(""),
    sourceTypes: str = Query("wiki,bank"),
    seedNodeId: str = Query(""),
    depth: int = Query(2, ge=1, le=3),
    limit: int = Query(80, ge=8, le=120),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        graph = await study_map_service.build_study_map(
            db,
            _uid(current_user),
            kb_id=int(kbId or 0),
            bank_ids=_parse_ids(bankIds),
            source_types=sourceTypes,
            seed_node_id=seedNodeId,
            depth=depth,
            limit=limit,
        )
        return success(graph)
    except Exception as exc:  # noqa: BLE001
        return error(f"读取学习图谱失败：{exc}")


@router.post("/study-plan/trace")
async def prepare_study_trace(
    data: TraceRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await study_advice_service.prepare_trace(
            db,
            _uid(current_user),
            kb_id=data.kbId,
            bank_ids=data.bankIds,
            source_types=data.sourceTypes,
            seed_node_id=data.seedNodeId,
            goal=data.goal,
            daily_minutes=data.dailyMinutes,
            horizon_days=data.horizonDays,
            instruction=data.instruction,
        )
        return success(payload)
    except Exception as exc:  # noqa: BLE001
        return error(f"生成学习轨迹失败：{exc}")


@router.post("/study-plan/advice/preview")
async def preview_study_advice(
    data: AdviceRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """节点点击后的轻量预览：用结构化模板快速给出阶段方向，不调用 LLM。"""
    try:
        payload = await study_advice_service.prepare_trace(
            db,
            _uid(current_user),
            kb_id=data.kbId,
            bank_ids=data.bankIds,
            source_types=data.sourceTypes,
            seed_node_id=data.seedNodeId,
            goal=data.goal,
            daily_minutes=data.dailyMinutes,
            horizon_days=data.horizonDays,
            instruction=data.instruction,
        )
        advice = study_advice_service.build_template_advice(
            payload["facts"],
            payload["trace"],
            instruction=data.instruction,
        )
        return success({"advice": advice, "trace": payload["trace"]})
    except Exception as exc:  # noqa: BLE001
        return error(f"生成规划建议预览失败：{exc}")


@router.post("/study-plan/advice")
async def generate_study_advice(
    data: AdviceRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        uid = _uid(current_user)
        payload = await study_advice_service.prepare_trace(
            db,
            uid,
            kb_id=data.kbId,
            bank_ids=data.bankIds,
            source_types=data.sourceTypes,
            seed_node_id=data.seedNodeId,
            goal=data.goal,
            daily_minutes=data.dailyMinutes,
            horizon_days=data.horizonDays,
            instruction=data.instruction,
        )
        trace = payload["trace"]
        facts = payload["facts"]
        advice = await study_advice_service.generate_advice(
            db,
            facts=facts,
            trace=trace,
            instruction=data.instruction,
            use_llm=bool(data.useLlm),
        )
        focus_ids = list((advice.get("scope") or {}).get("nodeIds") or [])
        focus_ids.extend(f"bank:{int(x)}" for x in (data.bankIds or []) if int(x) > 0)
        graph = study_advice_service.focus_graph(payload.get("graph") or {}, focus_ids)
        snapshot_id = 0
        if data.save:
            saved = await study_plan_history_service.save_snapshot(
                db,
                user_id=uid,
                kb_id=data.kbId,
                title=str(advice.get("title") or ""),
                scope=advice.get("scope") or {},
                advice=advice,
                trace=trace,
                graph=graph,
                parent_id=data.parentSnapshotId,
                source="page",
            )
            snapshot_id = int(saved.get("id") or 0)
        return success(
            {
                "advice": advice,
                "trace": trace,
                "graph": graph,
                "snapshotId": snapshot_id,
                "saved": bool(data.save),
                "traceId": trace.get("traceId") or data.traceId,
                "degraded": advice.get("degraded") or {},
            }
        )
    except Exception as exc:  # noqa: BLE001
        return error(f"生成规划建议失败：{exc}")


@router.post("/study-plan/advice/export")
async def export_study_advice(
    data: AdviceExportRequest,
    current_user: dict = Depends(get_current_user),
):
    """导出规划建议：PDF / TXT / Markdown。PNG 由前端画布直接生成。"""
    try:
        content, filename, media_type = study_advice_export_service.export_advice(data.advice, data.format)
        from urllib.parse import quote

        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )
    except ValueError as exc:
        return error(str(exc))
    except Exception as exc:  # noqa: BLE001
        return error(f"导出规划建议失败：{exc}")


@router.post("/study-plan/history")
async def create_study_history(
    data: HistorySaveRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        saved = await study_plan_history_service.save_snapshot(
            db,
            user_id=_uid(current_user),
            kb_id=data.kbId,
            title=data.title,
            scope=data.scope,
            advice=data.advice,
            trace=data.trace,
            graph=data.graph,
            parent_id=data.parentId,
            source=data.source,
        )
        return success(saved)
    except Exception as exc:  # noqa: BLE001
        return error(f"保存规划建议失败：{exc}")


@router.get("/study-plan/history")
async def list_study_history(
    limit: int = Query(20, ge=1, le=100),
    keyword: str = Query(""),
    seedNodeId: str = Query(""),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        items = await study_plan_history_service.list_snapshots(
            db, user_id=_uid(current_user), limit=limit, keyword=keyword, seed_node_id=seedNodeId
        )
        return success({"items": items})
    except Exception as exc:  # noqa: BLE001
        return error(f"读取规划建议历史失败：{exc}")


@router.get("/study-plan/history/{snapshot_id}")
async def get_study_history(
    snapshot_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await study_plan_history_service.get_snapshot(
            db, user_id=_uid(current_user), snapshot_id=snapshot_id
        )
        if not item:
            return error("规划建议不存在或不属于当前用户", 404)
        return success(item)
    except Exception as exc:  # noqa: BLE001
        return error(f"读取规划建议失败：{exc}")


@router.patch("/study-plan/history/{snapshot_id}")
async def patch_study_history(
    snapshot_id: int,
    data: HistoryPatchRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await study_plan_history_service.update_snapshot(
            db,
            user_id=_uid(current_user),
            snapshot_id=snapshot_id,
            title=data.title,
            pinned=data.pinned,
        )
        if not item:
            return error("规划建议不存在或不属于当前用户", 404)
        return success(item)
    except Exception as exc:  # noqa: BLE001
        return error(f"更新规划建议失败：{exc}")


@router.delete("/study-plan/history/{snapshot_id}")
async def delete_study_history(
    snapshot_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        ok = await study_plan_history_service.delete_snapshot(
            db, user_id=_uid(current_user), snapshot_id=snapshot_id
        )
        if not ok:
            return error("规划建议不存在或不属于当前用户", 404)
        return success({"id": snapshot_id, "deleted": True})
    except Exception as exc:  # noqa: BLE001
        return error(f"删除规划建议失败：{exc}")


__all__ = ["router"]
