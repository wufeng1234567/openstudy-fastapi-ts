"""画廊：把散落在文档 / 聊天里的图片汇总成可搜索、可描述、可定位的资产。

设计约束（0.4.x）
------------------
1. **不复制原图**。原图仍由 `rag_document.image_map` / `chat_upload_image` 持有，
   本服务只维护索引和描述缓存。
2. **描述默认不跑**。上传/同步时状态是 `pending`，用户主动点「补全」才调用模型。
3. **不伪造**。模型失败就保留 `failed` 和错误原因，不把空描述伪装成结果。
4. **稳定键**。`asset_key` 与 `material_asset_usage` 完全一致，引用/插入题目共用。
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_upload import ChatUploadImage
from app.models.content import ContentReference, RagImageAsset, RagImageDescribeJob
from app.models.note import Note
from app.models.question import QuestionMain
from app.models.rag import MaterialAssetUsage, RagDocument
from app.services.ai.base_client import ChatMessage, ImageBlock, TextBlock
from app.services.ai.chat_engine import stored_image_to_data_url
from app.services.ai.db_config import chat_with_config, resolve_config
from app.services.ai.model_capabilities import DEFAULT_VISION_MODEL, supports_vision
from app.services.rag.section_outline import content_sections
from app.services.rag.workspace_service import visible_image_map


def _section_for_marker(raw: str, seq: str) -> Dict[str, Any]:
    """找【图N】所在章节和附近文字（不依赖解析器，原文缺失也能返回空）。"""
    text = raw or ""
    marker = f"【图{seq}】"
    offset = text.find(marker)
    section = None
    if offset >= 0:
        for item in content_sections(text):
            if int(item.get("start", 0)) <= offset < int(item.get("end", len(text))):
                section = item
                break
    if offset < 0:
        return {"offset": None, "sectionIndex": None, "sectionTitle": "", "surrounding": ""}
    start = max(0, offset - 140)
    end = min(len(text), offset + len(marker) + 180)
    context = re.sub(r"\s+", " ", text[start:end]).strip()
    return {
        "offset": offset,
        "sectionIndex": int(section.get("index")) if section else None,
        "sectionTitle": str(section.get("title") or "") if section else "",
        "surrounding": context[:360],
    }


def _source_type(key: str) -> str:
    return "chat" if str(key or "").startswith("chat:") else "document"


def _asset_key_for_doc(doc_id: int, seq: Any) -> str:
    return f"doc:{int(doc_id)}:{str(seq)}"


def _asset_key_for_chat(image_id: int) -> str:
    return f"chat:{int(image_id)}"


def _infer_kind(file_name: str, url: str) -> str:
    name = f"{file_name or ''} {url or ''}".lower()
    if any(token in name for token in ("table", "表", "sheet")):
        return "table"
    if any(token in name for token in ("formula", "公式", "eq")):
        return "formula"
    if any(token in name for token in ("screenshot", "截图", "screen")):
        return "screenshot"
    if any(token in name for token in ("diagram", "图", "chart", "flow", "电路", "几何")):
        return "diagram"
    return "photo"


def _asset_dict(row: RagImageAsset, usage_count: int = 0, reference_count: int = 0) -> Dict[str, Any]:
    return {
        "assetKey": row.asset_key,
        "sourceType": row.source_type,
        "sourceName": row.source_name,
        "docId": row.doc_id,
        "kbId": row.kb_id,
        "url": row.url,
        "rawUrl": row.url,
        "fileName": row.file_name,
        "kind": row.kind or "image",
        "sectionIndex": row.section_index,
        "sectionTitle": row.section_title or "",
        "offset": row.offset,
        "surroundingText": row.surrounding_text or "",
        "caption": row.caption or "",
        "ocrText": row.ocr_text or "",
        "keywords": row.keywords or [],
        "descriptionStatus": row.description_status or "pending",
        "descriptionModel": row.description_model or "",
        "describeError": row.describe_error or "",
        "describedAt": row.described_at.strftime("%Y-%m-%d %H:%M") if row.described_at else "",
        "usedCount": int(usage_count or 0),
        "referenceCount": int(reference_count or 0),
        "createTime": row.create_time.strftime("%Y-%m-%d %H:%M") if row.create_time else "",
    }


async def _existing_map(db: AsyncSession, user_id: int) -> Dict[str, RagImageAsset]:
    rows = (
        await db.execute(select(RagImageAsset).where(RagImageAsset.user_id == int(user_id)))
    ).scalars().all()
    return {str(row.asset_key): row for row in rows}


async def sync_image_assets(db: AsyncSession, user_id: int) -> None:
    """把当前用户的文档图片和聊天图片补进索引。

    幂等：按 `(user_id, asset_key)` upsert；已描述状态不因为再次同步回退。
    """
    uid = int(user_id)
    existing = await _existing_map(db, uid)
    docs = (
        await db.execute(select(RagDocument).where(RagDocument.user_id == uid))
    ).scalars().all()
    seen: set[str] = set()

    for doc in docs:
        image_map = visible_image_map(doc)
        for seq, url in image_map.items():
            key = _asset_key_for_doc(doc.id, seq)
            seen.add(key)
            meta = _section_for_marker(doc.raw_content or "", str(seq))
            row = existing.get(key)
            if row is None:
                row = RagImageAsset(
                    user_id=uid,
                    kb_id=doc.kb_id,
                    doc_id=doc.id,
                    asset_key=key,
                    source_type="document",
                    url=str(url or ""),
                    file_name=f"{doc.file_name} · 图{int(seq) + 1}",
                    source_name=doc.file_name or "未命名资料",
                    kind=_infer_kind(doc.file_name or "", str(url or "")),
                    section_index=meta["sectionIndex"],
                    section_title=meta["sectionTitle"],
                    offset=meta["offset"],
                    surrounding_text=meta["surrounding"],
                    description_status="pending",
                )
                db.add(row)
                existing[key] = row
            else:
                row.kb_id = doc.kb_id
                row.doc_id = doc.id
                row.url = str(url or "")
                row.file_name = f"{doc.file_name} · 图{int(seq) + 1}"
                row.source_name = doc.file_name or "未命名资料"
                row.section_index = meta["sectionIndex"]
                row.section_title = meta["sectionTitle"]
                row.offset = meta["offset"]
                row.surrounding_text = meta["surrounding"]

    chat_images = (
        await db.execute(
            select(ChatUploadImage)
            .where(
                ChatUploadImage.user_id == uid,
                ChatUploadImage.deleted == 0,
            )
            .order_by(ChatUploadImage.create_time.desc())
            .limit(500)
        )
    ).scalars().all()
    for image in chat_images:
        key = _asset_key_for_chat(image.id)
        seen.add(key)
        row = existing.get(key)
        if row is None:
            row = RagImageAsset(
                user_id=uid,
                kb_id=None,
                doc_id=None,
                asset_key=key,
                source_type="chat",
                url=image.url or "",
                file_name=image.image_name or f"聊天图片 {image.id}",
                source_name="聊天图片",
                kind=_infer_kind(image.image_name or "", image.url or ""),
                section_title="",
                surrounding_text="",
                description_status="pending",
            )
            db.add(row)
            existing[key] = row
        else:
            row.url = image.url or row.url
            row.file_name = image.image_name or row.file_name
            row.source_name = "聊天图片"

    # 已被删除的聊天图 / 文档图：不删索引（描述可能还有价值），但标成不可用由列表过滤。
    await db.flush()


def _matches_q(row: RagImageAsset, q: str) -> bool:
    if not q:
        return True
    haystack = " ".join(
        [
            row.caption or "",
            row.ocr_text or "",
            row.file_name or "",
            row.source_name or "",
            row.section_title or "",
            " ".join(str(x) for x in (row.keywords or [])),
        ]
    ).lower()
    return q.lower() in haystack


async def list_gallery(
    db: AsyncSession,
    user_id: int,
    *,
    scope: str = "all",
    kb_id: Optional[int] = None,
    doc_id: Optional[int] = None,
    source: str = "all",
    status: str = "all",
    q: str = "",
    limit: int = 200,
) -> Dict[str, Any]:
    """返回画廊卡片 + 真实统计；不生成任何“示例数据”。"""
    await sync_image_assets(db, user_id)
    rows = (
        await db.execute(
            select(RagImageAsset)
            .where(RagImageAsset.user_id == int(user_id))
            .order_by(RagImageAsset.create_time.desc(), RagImageAsset.id.desc())
        )
    ).scalars().all()

    # 软删除文档 / 已从正文移除的图片，不应继续出现在画廊里。
    active_docs = (
        await db.execute(select(RagDocument).where(RagDocument.user_id == int(user_id)))
    ).scalars().all()
    active_doc_ids = {int(doc.id) for doc in active_docs}
    active_doc_urls = {
        int(doc.id): set(str(url) for url in visible_image_map(doc).values())
        for doc in active_docs
    }
    active_chat_ids = set(
        (
            await db.execute(
                select(ChatUploadImage.id).where(
                    ChatUploadImage.user_id == int(user_id),
                    ChatUploadImage.deleted == 0,
                )
            )
        ).scalars().all()
    )

    # scope / kb 过滤先做；统计也只统计当前范围，避免“全部”数字误导。
    scoped: List[RagImageAsset] = []
    document_options_map: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        if row.source_type == "document":
            if row.doc_id not in active_doc_ids or str(row.url) not in active_doc_urls.get(int(row.doc_id), set()):
                continue
            did = int(row.doc_id or 0)
            if did:
                item = document_options_map.setdefault(
                    did,
                    {"docId": did, "fileName": row.source_name or f"文档#{did}", "count": 0},
                )
                item["count"] = int(item["count"]) + 1
        elif row.source_type == "chat":
            try:
                chat_id = int(str(row.asset_key).rsplit(":", 1)[-1])
            except (TypeError, ValueError):
                chat_id = 0
            if chat_id not in active_chat_ids:
                continue
        if scope == "current" and kb_id is not None and int(row.kb_id or 0) != int(kb_id):
            continue
        if doc_id is not None and int(row.doc_id or 0) != int(doc_id):
            continue
        scoped.append(row)

    usage_rows = (
        await db.execute(
            select(MaterialAssetUsage.asset_key, func.count(MaterialAssetUsage.id))
            .where(
                MaterialAssetUsage.user_id == int(user_id),
                MaterialAssetUsage.deleted == 0,
            )
            .group_by(MaterialAssetUsage.asset_key)
        )
    ).all()
    usage_map = {str(k): int(v) for k, v in usage_rows}
    ref_rows = (
        await db.execute(
            select(ContentReference.source_type, ContentReference.source_id, ContentReference.source_sub_id)
            .where(ContentReference.user_id == int(user_id), ContentReference.deleted == 0)
        )
    ).all()
    ref_map: Dict[str, int] = {}
    for source_type, source_id, sub_id in ref_rows:
        if source_type == "document_image":
            key = f"doc:{int(source_id)}:{sub_id or ''}"
        elif source_type == "chat_image":
            key = f"chat:{int(source_id)}"
        else:
            continue
        ref_map[key] = ref_map.get(key, 0) + 1

    stats_total = len(scoped)
    stats_done = sum(1 for row in scoped if row.description_status == "done")
    stats_failed = sum(1 for row in scoped if row.description_status == "failed")
    stats_pending = stats_total - stats_done - stats_failed
    stats_used = sum(1 for row in scoped if usage_map.get(row.asset_key, 0) > 0)
    source_counts = {
        "document": sum(1 for row in scoped if row.source_type == "document"),
        "chat": sum(1 for row in scoped if row.source_type == "chat"),
    }

    filtered = []
    for row in scoped:
        if source != "all" and row.source_type != source:
            continue
        if status != "all" and row.description_status != status:
            continue
        if not _matches_q(row, q.strip()):
            continue
        filtered.append(row)

    items = [
        _asset_dict(
            row,
            usage_count=usage_map.get(row.asset_key, 0),
            reference_count=ref_map.get(row.asset_key, 0),
        )
        for row in filtered[: max(1, min(int(limit or 200), 500))]
    ]
    document_options = sorted(
        document_options_map.values(), key=lambda item: str(item["fileName"])
    )
    return {
        "items": items,
        "stats": {
            "total": stats_total,
            "described": stats_done,
            "pending": stats_pending,
            "failed": stats_failed,
            "used": stats_used,
        },
        "sources": [
            {"key": "all", "label": "全部图片", "count": stats_total},
            {"key": "document", "label": "文档图片", "count": source_counts["document"]},
            {"key": "chat", "label": "聊天图片", "count": source_counts["chat"]},
        ],
        "documents": document_options,
        "scope": scope,
        "query": q,
    }


async def get_asset_detail(db: AsyncSession, user_id: int, asset_key: str) -> Dict[str, Any]:
    await sync_image_assets(db, user_id)
    row = (
        await db.execute(
            select(RagImageAsset).where(
                RagImageAsset.user_id == int(user_id),
                RagImageAsset.asset_key == str(asset_key),
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise ValueError("图片资产不存在或无权访问")

    usages = (
        await db.execute(
            select(MaterialAssetUsage).where(
                MaterialAssetUsage.user_id == int(user_id),
                MaterialAssetUsage.asset_key == str(asset_key),
                MaterialAssetUsage.deleted == 0,
            )
        )
    ).scalars().all()
    usage_items: List[Dict[str, Any]] = []
    note_ids = [int(u.target_id) for u in usages if u.target_type == "note"]
    question_ids = [int(u.target_id) for u in usages if u.target_type == "question"]
    note_titles: Dict[int, str] = {}
    question_titles: Dict[int, str] = {}
    if note_ids:
        for note in (await db.execute(select(Note).where(Note.note_id.in_(note_ids)))).scalars().all():
            note_titles[int(note.note_id)] = note.title or "未命名笔记"
    if question_ids:
        for question in (
            await db.execute(select(QuestionMain).where(QuestionMain.id.in_(question_ids)))
        ).scalars().all():
            question_titles[int(question.id)] = (question.question_text or question.content or "未命名题目")[:72]
    for usage in usages:
        title = ""
        if usage.target_type == "note":
            title = note_titles.get(int(usage.target_id), "笔记")
        elif usage.target_type == "question":
            title = question_titles.get(int(usage.target_id), "题目")
        else:
            title = "文档"
        usage_items.append(
            {
                "targetType": usage.target_type,
                "targetId": usage.target_id,
                "title": title,
                "createTime": usage.create_time.strftime("%Y-%m-%d %H:%M") if usage.create_time else "",
            }
        )

    if row.source_type == "document" and row.doc_id:
        references = (
            await db.execute(
                select(ContentReference).where(
                    ContentReference.user_id == int(user_id),
                    ContentReference.deleted == 0,
                    ContentReference.source_type == "document_image",
                    ContentReference.source_id == int(row.doc_id),
                )
            )
        ).scalars().all()
        references = [
            ref for ref in references
            if str(ref.source_sub_id or "") == str(row.asset_key.rsplit(":", 1)[-1])
        ]
    else:
        try:
            chat_image_id = int(row.asset_key.rsplit(":", 1)[-1])
        except (TypeError, ValueError):
            chat_image_id = 0
        references = (
            await db.execute(
                select(ContentReference).where(
                    ContentReference.user_id == int(user_id),
                    ContentReference.deleted == 0,
                    ContentReference.source_type == "chat_image",
                    ContentReference.source_id == chat_image_id,
                )
            )
        ).scalars().all()

    reference_items: List[Dict[str, Any]] = []
    if references:
        from app.services.rag import reference_service

        for ref in references[:12]:
            try:
                enriched = await reference_service.get_reference(db, user_id, ref.id)
                reference_items.append(
                    {
                        "id": ref.id,
                        "targetType": enriched.get("targetType"),
                        "targetTitle": (enriched.get("target") or {}).get("title") or "未命名对象",
                        "quote": enriched.get("quote") or "",
                        "createTime": enriched.get("createTime") or "",
                    }
                )
            except ValueError:
                continue

    payload = _asset_dict(row, usage_count=len(usage_items), reference_count=len(reference_items))
    payload["usages"] = usage_items
    payload["references"] = reference_items
    payload["sourceTypeLabel"] = "聊天图片" if row.source_type == "chat" else "文档图片"
    payload["canLocate"] = bool(row.doc_id and row.offset is not None)
    return payload


def _parse_json_payload(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型没有返回可解析的 JSON")
    data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("模型返回的不是 JSON 对象")
    return data


def _description_prompt(row: RagImageAsset) -> str:
    return (
        "你是学习资料的图片索引助手。请只根据图片本身和给定上下文，生成可检索的图片索引。\n"
        "要求：\n"
        "1. caption 用中文说清楚这张图“是什么、表达什么”，不要写空话；\n"
        "2. ocrText 只抄写图片中清晰可见的文字/公式，看不清就留空，禁止编造；\n"
        "3. kind 从 photo / diagram / table / formula / screenshot 中选一个；\n"
        "4. keywords 给 3 到 6 个短词，便于搜索；\n"
        "5. 只输出一个 JSON 对象，不要 Markdown。\n\n"
        f"来源资料：{row.source_name or '未知'}\n"
        f"所在章节：{row.section_title or '未识别'}\n"
        f"图片附近文字：{row.surrounding_text or '无'}\n"
        f"已有 OCR：{row.ocr_text or '无'}\n\n"
        '输出格式：{"caption":"...","ocrText":"...","kind":"diagram","keywords":["..."]}'
    )


async def describe_asset(
    db: AsyncSession,
    user_id: int,
    asset_key: str,
) -> Dict[str, Any]:
    """对单张图片调用视觉模型并写回索引。失败时保留失败状态，不伪造描述。"""
    row = (
        await db.execute(
            select(RagImageAsset).where(
                RagImageAsset.user_id == int(user_id),
                RagImageAsset.asset_key == str(asset_key),
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise ValueError("图片资产不存在或无权访问")

    row.description_status = "processing"
    row.describe_error = ""
    await db.flush()

    try:
        data_url = stored_image_to_data_url(row.url or "")
        if not data_url:
            raise ValueError("原图读取失败，无法生成描述")
        # 选一个明确支持视觉的模型；没有配置时仍交给默认路由，失败会如实返回。
        config = await resolve_config(db, provider=None, model=None, user_id=int(user_id))
        model = config.model if config and supports_vision(config.model) else DEFAULT_VISION_MODEL
        messages = [
            ChatMessage(role="system", content="你只输出严格 JSON，不输出客套话。"),
            ChatMessage(
                role="user",
                content=[
                    TextBlock(type="text", text=_description_prompt(row)),
                    ImageBlock(type="image_url", image_url={"url": data_url}),
                ],
            ),
        ]
        response = await chat_with_config(
            db,
            messages,
            model=model,
            temperature=0.2,
            max_tokens=1200,
            user_id=int(user_id),
        )
        parsed = _parse_json_payload(response.content or "")
        row.caption = str(parsed.get("caption") or "").strip()
        row.ocr_text = str(parsed.get("ocrText") or parsed.get("ocr_text") or "").strip()
        kind = str(parsed.get("kind") or "").strip().lower()
        if kind in {"photo", "diagram", "table", "formula", "screenshot"}:
            row.kind = kind
        keywords = parsed.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [x.strip() for x in re.split(r"[,，、\s]+", keywords) if x.strip()]
        row.keywords = [str(x).strip()[:40] for x in keywords][:8] if isinstance(keywords, list) else []
        row.description_status = "done"
        row.description_model = model
        row.described_at = datetime.now()
        row.update_time = datetime.now()
        await db.commit()
        return _asset_dict(row)
    except Exception as exc:  # noqa: BLE001 - 单张失败不拖垮整批
        row.description_status = "failed"
        row.describe_error = str(exc)[:480]
        row.update_time = datetime.now()
        await db.commit()
        raise


def _job_dict(job: RagImageDescribeJob) -> Dict[str, Any]:
    return {
        "jobId": int(job.id),
        "status": job.status,
        "total": int(job.total or 0),
        "done": int(job.done or 0),
        "failed": int(job.failed or 0),
        "currentAssetKey": job.current_asset_key or "",
        "error": job.error or "",
        "active": job.status == "running",
        "createTime": job.create_time.strftime("%Y-%m-%d %H:%M:%S") if job.create_time else "",
        "finishedAt": job.finished_at.strftime("%Y-%m-%d %H:%M:%S") if job.finished_at else "",
    }


async def _select_describe_rows(
    db: AsyncSession,
    user_id: int,
    *,
    asset_keys: Optional[Iterable[str]] = None,
    doc_id: Optional[int] = None,
    limit: int = 40,
) -> List[RagImageAsset]:
    query = select(RagImageAsset).where(RagImageAsset.user_id == int(user_id))
    if doc_id is not None:
        query = query.where(RagImageAsset.doc_id == int(doc_id))
    if asset_keys:
        keys = [str(x) for x in asset_keys if str(x)]
        if keys:
            query = query.where(RagImageAsset.asset_key.in_(keys))
    query = query.order_by(RagImageAsset.create_time.asc()).limit(max(1, min(int(limit or 40), 40)))
    return list((await db.execute(query)).scalars().all())


async def create_describe_job(
    db: AsyncSession,
    user_id: int,
    *,
    asset_keys: Optional[Iterable[str]] = None,
    doc_id: Optional[int] = None,
    limit: int = 40,
) -> tuple[Dict[str, Any], List[str], bool]:
    """创建批量描述任务；已有运行中的任务时直接复用，避免重复调用视觉模型。

    返回 `(job, asset_keys, created)`：`created=False` 表示复用已有运行中任务。
    """
    await sync_image_assets(db, user_id)
    active = (
        await db.execute(
            select(RagImageDescribeJob)
            .where(
                RagImageDescribeJob.user_id == int(user_id),
                RagImageDescribeJob.status == "running",
            )
            .order_by(RagImageDescribeJob.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if active is not None:
        return _job_dict(active), [str(x) for x in (active.asset_keys or [])], False

    rows = await _select_describe_rows(
        db, user_id, asset_keys=asset_keys, doc_id=doc_id, limit=limit
    )
    keys = [row.asset_key for row in rows]
    if not keys:
        return {
            "jobId": 0,
            "status": "done",
            "total": 0,
            "done": 0,
            "failed": 0,
            "currentAssetKey": "",
            "error": "",
            "active": False,
        }, [], False
    job = RagImageDescribeJob(
        user_id=int(user_id),
        status="running",
        total=len(keys),
        done=0,
        failed=0,
        asset_keys=keys,
        update_time=datetime.now(),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return _job_dict(job), keys, True


async def run_describe_job(job_id: int, user_id: int, asset_keys: List[str]) -> None:
    """后台执行批量描述：3 路并发调用视觉模型，逐张回写任务进度。"""
    if not asset_keys:
        return
    semaphore = asyncio.Semaphore(3)

    async def one(key: str) -> tuple[str, bool]:
        async with semaphore:
            try:
                from app.database import async_session_factory

                async with async_session_factory() as session:
                    await describe_asset(session, int(user_id), key)
                return key, True
            except Exception:  # noqa: BLE001 - 单张失败不拖垮整批
                return key, False

    tasks = [asyncio.create_task(one(key)) for key in asset_keys]
    try:
        for completed in asyncio.as_completed(tasks):
            key, ok = await completed
            from app.database import async_session_factory

            async with async_session_factory() as job_db:
                job = await job_db.get(RagImageDescribeJob, int(job_id))
                if job is None:
                    continue
                job.done = int(job.done or 0) + 1
                if not ok:
                    job.failed = int(job.failed or 0) + 1
                job.current_asset_key = key
                job.update_time = datetime.now()
                await job_db.commit()
        from app.database import async_session_factory

        async with async_session_factory() as job_db:
            job = await job_db.get(RagImageDescribeJob, int(job_id))
            if job is not None:
                job.status = "done"
                job.current_asset_key = ""
                job.finished_at = datetime.now()
                job.update_time = datetime.now()
                await job_db.commit()
    except Exception as exc:  # noqa: BLE001
        from app.database import async_session_factory

        async with async_session_factory() as job_db:
            job = await job_db.get(RagImageDescribeJob, int(job_id))
            if job is not None:
                job.status = "failed"
                job.error = str(exc)[:480]
                job.current_asset_key = ""
                job.finished_at = datetime.now()
                job.update_time = datetime.now()
                await job_db.commit()


async def get_describe_job(
    db: AsyncSession, user_id: int, job_id: int
) -> Dict[str, Any]:
    job = (
        await db.execute(
            select(RagImageDescribeJob).where(
                RagImageDescribeJob.id == int(job_id),
                RagImageDescribeJob.user_id == int(user_id),
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise ValueError("图片描述任务不存在或无权访问")
    return _job_dict(job)


async def get_latest_describe_job(db: AsyncSession, user_id: int) -> Optional[Dict[str, Any]]:
    job = (
        await db.execute(
            select(RagImageDescribeJob)
            .where(RagImageDescribeJob.user_id == int(user_id))
            .order_by(RagImageDescribeJob.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return _job_dict(job) if job else None


async def describe_assets(
    db: AsyncSession,
    user_id: int,
    *,
    asset_keys: Optional[Iterable[str]] = None,
    doc_id: Optional[int] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    await sync_image_assets(db, user_id)
    query = select(RagImageAsset).where(RagImageAsset.user_id == int(user_id))
    if doc_id is not None:
        query = query.where(RagImageAsset.doc_id == int(doc_id))
    if asset_keys:
        keys = [str(x) for x in asset_keys if str(x)]
        if keys:
            query = query.where(RagImageAsset.asset_key.in_(keys))
    query = query.order_by(RagImageAsset.create_time.asc()).limit(max(1, min(int(limit or 20), 40)))
    rows = (await db.execute(query)).scalars().all()
    done = 0
    failed = 0
    items: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    for row in rows:
        try:
            item = await describe_asset(db, user_id, row.asset_key)
            done += 1
            items.append(item)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append({"assetKey": row.asset_key, "error": str(exc)[:200]})
    return {"total": len(rows), "done": done, "failed": failed, "items": items, "errors": errors}


__all__ = [
    "sync_image_assets",
    "list_gallery",
    "get_asset_detail",
    "describe_asset",
    "describe_assets",
    "create_describe_job",
    "run_describe_job",
    "get_describe_job",
    "get_latest_describe_job",
]
