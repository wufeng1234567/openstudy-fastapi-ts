"""
默认知识库（原「工作空间 / 我的空间」）服务

产品定位
========
每个用户有一个**默认知识库**，新传的资料先落这里，不用先想「该放哪个库」。
之后在对话里说「用我那份概率论的资料出题」，AI 会**自己去库找**，不需要手动选文件。

⚠️ 2026-10-22 改名：这个模块原来叫「工作空间 / 我的空间」，
   现已统一并入「知识库」—— 侧栏入口改名为「知识库」，
   页面升级为完整的多知识库管理（见 `views/front/workspace/index.vue`）。
   代码里的 `workspace` 标识（表字段 `is_workspace`、`/rag/workspace/*` 接口）
   **保持不动**：改名只是产品文案层面的事，动标识要连带迁移数据与工具调用，不值得。

为什么复用知识库（`rag_knowledge_base`）
=====================================
默认库里的文件同样要「解析 → 分块 → 向量化 → 被 AI 检索」 —— 和普通知识库是同一条链路。
新建一张表等于把这套逻辑抄第二遍（早晚漂移），而且 `knowledge_search` 工具
还得再写一份。所以这里只是给知识库加了一个 `is_workspace=1` 标记：
每个用户有且仅有一个这样的库。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.rag import (
    MaterialOrganizeLog,
    MaterialOrganizePlan,
    RagDocument,
    RagKnowledgeBase,
)
from app.services.material_organizer import (
    analyze as analyze_material,
    build_blocks,
    duplicate_blocks,
    garbage_blocks,
    image_layout,
    image_links,
    noise_blocks,
    off_topic_blocks,
    question_groups,
)
from app.services.material_structure import apply_layouts, build_structure_plan, layout_ranges

#: 默认资料夹在界面上显示的名字（用户不可改）
#: 与普通资料夹并列展示，所以名字要像"一个资料夹"，而不是"一个特殊区域"
WORKSPACE_NAME = "默认资料夹"
WORKSPACE_DESC = "新传的资料先放这里，AI 会自己找"


async def get_or_create_workspace(db: AsyncSession, user_id: int) -> RagKnowledgeBase:
    """取该用户的工作空间；没有就建一个。

    幂等：并发情况下靠 `uk_kb_workspace_per_user` 部分唯一索引兜底。
    """
    row = (
        await db.execute(
            select(RagKnowledgeBase).where(
                and_(
                    RagKnowledgeBase.user_id == user_id,
                    RagKnowledgeBase.is_workspace == 1,
                    RagKnowledgeBase.del_flag == "0",
                )
            )
        )
    ).scalar_one_or_none()
    if row:
        return row

    kb = RagKnowledgeBase(
        user_id=user_id,
        name=WORKSPACE_NAME,
        description=WORKSPACE_DESC,
        is_workspace=1,
        status="0",
        del_flag="0",
        doc_count=0,
        chunk_count=0,
    )
    db.add(kb)
    try:
        await db.flush()
    except Exception:
        # 并发下可能已被另一个请求建好 —— 回滚后重查
        await db.rollback()
        row = (
            await db.execute(
                select(RagKnowledgeBase).where(
                    and_(
                        RagKnowledgeBase.user_id == user_id,
                        RagKnowledgeBase.is_workspace == 1,
                        RagKnowledgeBase.del_flag == "0",
                    )
                )
            )
        ).scalar_one_or_none()
        if row:
            return row
        raise
    return kb


async def list_space_files(db: AsyncSession, user_id: int) -> List[Dict[str, Any]]:
    """列出默认知识库里的文件"""
    kb = await get_or_create_workspace(db, user_id)
    return await _files_of_kb(db, kb.id)


def visible_image_map(doc: RagDocument) -> Dict[str, str]:
    """返回展示/图片墙用的图片清单，过滤掉被软剔除的图片。

    `image_map` 是原始全文的资产清单，不能因为用户没删除文件就永远显示；
    图片标记落在 excluded_ranges 内时，图片墙、资料卡片图片数和解剖都不应再展示。
    """
    raw = doc.raw_content or ""
    ranges = doc.excluded_ranges or []
    visible: Dict[str, str] = {}
    for key, url in (doc.image_map or {}).items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        marker = f"【图{index}】"
        pos = raw.find(marker)
        hidden = False
        if pos >= 0:
            end = pos + len(marker)
            for item in ranges:
                try:
                    start = int(item.get("start", -1))
                    stop = int(item.get("end", -1))
                except (AttributeError, TypeError, ValueError):
                    continue
                if start < end and stop > pos:
                    hidden = True
                    break
        if not hidden:
            visible[str(index)] = url
    return visible


async def _files_of_kb(db: AsyncSession, kb_id: int) -> List[Dict[str, Any]]:
    """某个知识库下的全部文档（含备注、分块数、解析状态）"""
    rows = (
        await db.execute(
            select(RagDocument)
            .where(RagDocument.kb_id == kb_id)
            .order_by(RagDocument.create_time.desc())
        )
    ).scalars().all()

    return [
        {
            "docId": d.id,
            "kbId": d.kb_id,
            "fileName": d.file_name,
            "originalFileName": d.original_file_name or d.file_name,
            "subject": (d.subject or analyze_material(d.file_name or "", d.raw_content or "", None, len(d.image_map or {}))["subject"]),
            "materialType": (d.material_type or analyze_material(d.file_name or "", d.raw_content or "", None, len(d.image_map or {}))["material_type"]),
            "facets": (d.facets or analyze_material(d.file_name or "", d.raw_content or "", None, len(d.image_map or {}))["facets"]),
            "fileType": d.file_type,
            "fileSize": d.file_size,
            "sizeText": _size_text(d.file_size or 0),
            "note": d.user_note or "",
            "chunkCount": d.chunk_count or 0,
            "status": d.status,
            "statusText": _status_text(d.status),
            "disabled": 1 if getattr(d, "disabled", 0) else 0,
            "errorMsg": d.error_msg or "",
            # 资料卡 facet / 图片墙用：图片清单本身不大，随文档列表一起返回，
            # 避免前端点一次文档再发一次请求。
            "imageCount": len(visible_image_map(d)),
            "imageMap": visible_image_map(d),
            "createTime": _format_display_time(d.create_time),
        }
        for d in rows
    ]


def _size_text(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


_STATUS = {1: "待解析", 2: "解析中", 3: "已解析", 4: "处理失败", 5: "可检索"}


def _status_text(s: Optional[int]) -> str:
    return _STATUS.get(int(s or 0), "未知")


# ============================================================
# AI 找文件
# ============================================================
#: 文件名/备注里命中的权重 > 正文命中，因为用户说的「那份概率论的资料」
#: 通常是在描述文件，不是在描述内容。
SCORE_FILENAME_HIT = 10
SCORE_NOTE_HIT = 8
SCORE_CONTENT_HIT = 1


def _tokens(text: str) -> List[str]:
    """把用户的一句话切成用于匹配的关键词。

    中文没有空格，简单按 2-4 字的滑窗切有噪音；这里用「去掉停用词后的连续片段」：
      · 英文/数字：按非字母数字切
      · 中文：整段保留，另外补上 2-3 族的二元组（「概率论」→「概率」「率论」）
    召回可以宽松，排序由分数兜。
    """
    text = (text or "").strip().lower()
    if not text:
        return []

    # 去掉常见无意义词（用户问句里的虚词）
    STOP = (
        "帮我", "用一下", "那个", "这份", "那份", "这个", "里面", "里的", "中的",
        "文件", "资料", "文档", "出题", "建个", "题库", "知识库", "生成", "一下",
        "我", "的", "了", "吧", "吗", "呢", "和", "与", "在", "把", "给", "从",
    )
    for w in STOP:
        text = text.replace(w, " ")

    out: List[str] = []
    for chunk in re.split(r"[\s,，。.、;；:：!！?？()（）\[\]【】]+", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        # 英文/数字整体算一个
        if re.fullmatch(r"[a-z0-9_\-./]+", chunk):
            if len(chunk) >= 2:
                out.append(chunk)
            continue
        # 中文：整段 + 二元组
        if len(chunk) >= 2:
            out.append(chunk)
        for i in range(len(chunk) - 1):
            bg = chunk[i : i + 2]
            if len(bg) == 2:
                out.append(bg)
    # 去重保序
    seen = set()
    uniq = []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq[:12]


async def search_files(
    db: AsyncSession, user_id: int, query: str, limit: int = 5
) -> List[Dict[str, Any]]:
    """在用户的工作空间里按「文件名 / 备注 / 正文」找最相关的文件。

    返回按相关度降序的文件摘要列表。空列表 = 没找到。
    """
    kb = await get_or_create_workspace(db, user_id)
    docs = (
        await db.execute(select(RagDocument).where(RagDocument.kb_id == kb.id))
    ).scalars().all()
    if not docs:
        return []

    tokens = _tokens(query)
    if not tokens:
        # 没有有效关键词 → 返回最近上传的几个（用户可能就是想看「我刚传的」）
        docs = sorted(docs, key=lambda d: d.create_time or 0, reverse=True)[:limit]
        return [_doc_brief(d, score=0) for d in docs]

    scored = []
    for d in docs:
        if getattr(d, "disabled", 0):
            continue
        name = (d.file_name or "").lower()
        note = (d.user_note or "").lower()
        content = (d.raw_content or "").lower()

        score = 0
        hits: List[str] = []
        for t in tokens:
            if t in name:
                score += SCORE_FILENAME_HIT
                hits.append(t)
            if note and t in note:
                score += SCORE_NOTE_HIT
                hits.append(t)
            if content and t in content:
                score += SCORE_CONTENT_HIT
        if score > 0:
            scored.append((score, d, hits))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [_doc_brief(d, score=s, hits=h) for s, d, h in scored[:limit]]


def _doc_brief(d: RagDocument, score: int = 0, hits: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "docId": d.id,
        "fileName": d.file_name,
        "note": d.user_note or "",
        "fileType": d.file_type,
        "sizeText": _size_text(d.file_size or 0),
        "chunkCount": d.chunk_count or 0,
        "status": d.status,
        "statusText": _status_text(d.status),
        "contentLength": len(d.raw_content or ""),
        "score": score,
        "matched": (hits or [])[:5],
        "createTime": _format_display_time(d.create_time)[:10] if d.create_time else None,
    }


async def space_stats(db: AsyncSession, user_id: int) -> Dict[str, Any]:
    """空间概况（给前端头部与 AI 提示用）"""
    kb = await get_or_create_workspace(db, user_id)
    doc_count = await db.scalar(
        select(func.count()).select_from(RagDocument).where(RagDocument.kb_id == kb.id)
    )
    total_size = await db.scalar(
        select(func.coalesce(func.sum(RagDocument.file_size), 0)).where(
            RagDocument.kb_id == kb.id
        )
    )
    ready = await db.scalar(
        select(func.count())
        .select_from(RagDocument)
        .where(and_(RagDocument.kb_id == kb.id, RagDocument.status == 5))
    )
    return {
        "kbId": kb.id,
        "docCount": int(doc_count or 0),
        "readyCount": int(ready or 0),
        "totalSize": int(total_size or 0),
        "totalSizeText": _size_text(int(total_size or 0)),
    }


# ============================================================
# 知识库总览（新版「知识库」整页的唯一数据源）
# ============================================================

async def overview(db: AsyncSession, user_id: int) -> Dict[str, Any]:
    """列出该用户**全部**知识库 + 每个库的文档，一次给全。

    为什么一次给全（而不是「先列库、点进去再拉文档」）
    ------------------------------------------------
    知识库的数量级很小（实测十几个），文档也就几十份。一次取完的好处：
      · 左边点库、右边**立刻**出文档，没有转圈等待；
      · 头部统计（共几个库 / 共几份资料）不用再发一个请求；
      · 前端不必维护「文档缓存失效」这一层，少一类 bug。

    返回结构
    --------
    {
      "stats": {kbCount, docCount, readyCount, totalSizeText},
      "knowledgeBases": [{kbId, name, description, isDefault, disabled,
                          docCount, chunkCount, createTime, files: [...]}]
    }

    ⚠️ 默认库（`is_workspace=1`）**也在这份列表里**，且排在最前面 ——
       它现在就是一个普通的知识库，不再是侧栏里那个独立的东西。
    """
    default_kb = await get_or_create_workspace(db, user_id)

    rows = (
        await db.execute(
            select(RagKnowledgeBase)
            .where(
                RagKnowledgeBase.user_id == user_id,
                RagKnowledgeBase.del_flag == "0",
            )
            .order_by(RagKnowledgeBase.create_time.desc(), RagKnowledgeBase.id.desc())
        )
    ).scalars().all()

    # 默认库排最前，其余保持「新的在前」
    ordered = [default_kb] + [k for k in rows if k.id != default_kb.id]

    kbs: List[Dict[str, Any]] = []
    total_docs = 0
    total_ready = 0
    total_size = 0

    for kb in ordered:
        files = await _files_of_kb(db, kb.id)
        for f in files:
            total_size += int(f.get("fileSize") or 0)
        ready = sum(1 for f in files if f.get("status") == 5)
        total_docs += len(files)
        total_ready += ready

        kbs.append(
            {
                "kbId": kb.id,
                "name": WORKSPACE_NAME if kb.is_workspace == 1 else kb.name,
                "description": kb.description or "",
                "isDefault": 1 if kb.is_workspace == 1 else 0,
                "disabled": 1 if kb.disabled == 1 else 0,
                "docCount": len(files),
                "chunkCount": sum(int(f.get("chunkCount") or 0) for f in files),
                "createTime": _format_display_time(kb.create_time)[:10] if kb.create_time else None,
                "files": files,
            }
        )

    return {
        "stats": {
            "kbCount": len(kbs),
            "docCount": total_docs,
            "readyCount": total_ready,
            "totalSize": total_size,
            "totalSizeText": _size_text(total_size),
        },
        "knowledgeBases": kbs,
        "defaultKbId": default_kb.id,
    }


# ============================================================
# 智能整理：整理快照 / diff / 整批回退
# ============================================================

def _rebuild_content_structure(raw: str) -> list:
    """正文被重排/编辑后重建块结构，避免沿用旧偏移误判代码/公式/表格。"""
    try:
        from app.services.file_parser import parse_file

        parsed = parse_file("document.md", (raw or "").encode("utf-8"))
        return parsed.get("contentStructure") or []
    except Exception:  # noqa: BLE001 - 结构重建失败不能阻断整理应用
        return []


def _doc_snapshot(doc: RagDocument) -> Dict[str, Any]:
    return {
        "docId": doc.id,
        "fileName": doc.file_name or "",
        "originalFileName": doc.original_file_name or doc.file_name or "",
        "subject": doc.subject or "",
        "materialType": doc.material_type or "",
        "facets": doc.facets or {},
        "excludedRanges": doc.excluded_ranges or [],
        # 图片搬运/重排会改 raw_content，回退时必须能恢复（文本通常只有几十 KB）。
        "rawContent": doc.raw_content or "",
        # 块结构跟着正文变；回退时一起恢复，避免下次整理拿错偏移。
        "contentStructure": doc.content_structure or [],
    }


def _doc_revision(doc: RagDocument) -> str:
    """计划应用时用于防止「预览后文档又变了」。"""
    raw = "|".join(
        [
            str(doc.id),
            doc.file_name or "",
            doc.subject or "",
            doc.material_type or "",
            repr(doc.facets or {}),
            repr(doc.excluded_ranges or []),
            repr(doc.content_structure or []),
            hashlib.sha256((doc.raw_content or "").encode("utf-8")).hexdigest(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _facet_rows(facets: Optional[Dict[str, Any]]) -> List[List[str]]:
    f = facets or {}
    return [
        ["词数", str(f.get("wordCount") or 0)],
        ["公式", str(f.get("formulaCount") or 0)],
        ["图片", str(f.get("imageCount") or 0)],
        ["表格", str(f.get("tableCount") or 0)],
        ["标题", str(f.get("headingCount") or 0)],
    ]


def _text(value: Any) -> Dict[str, Any]:
    return {"type": "text", "value": "" if value is None else str(value)}


def _image_value(label: str, url: str, position: str = "") -> Dict[str, Any]:
    return {
        "type": "image",
        "value": label + (f" · {position}" if position else ""),
        "label": label,
        "url": url,
        "position": position,
    }


def _table(rows: List[List[str]]) -> Dict[str, Any]:
    return {"type": "table", "headers": ["指标", "值"], "rows": rows}


def _list(values: List[Any]) -> Dict[str, Any]:
    return {"type": "list", "value": values}


def _change(
    change_id: str,
    group: str,
    field: str,
    label: str,
    before: Any,
    after: Any,
    reason: str,
    *,
    risk: str = "low",
    confidence: float = 1.0,
    selectable: bool = True,
    action: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    item = {
        "id": change_id,
        "group": group,
        "field": field,
        "label": label,
        "before": before,
        "after": after,
        "reason": reason,
        "risk": risk,
        "confidence": round(float(confidence), 2),
        "selectable": selectable,
    }
    if action:
        item["action"] = action
    if extra:
        item.update(extra)
    return item


def _quick_changes(doc: RagDocument, result: Dict[str, Any]) -> List[Dict[str, Any]]:
    changes: List[Dict[str, Any]] = []
    before_facets = doc.facets or {}
    after_facets = result.get("facets") or {}
    if (doc.file_name or "") != result.get("display_name"):
        changes.append(
            _change(
                "filename",
                "meta",
                "fileName",
                "文件名",
                _text(doc.file_name or ""),
                _text(result.get("display_name") or ""),
                "去掉上传链路 hash 前缀或替换无意义文件名",
            )
        )
    if (doc.subject or "未分类") != result.get("subject"):
        changes.append(
            _change(
                "subject",
                "meta",
                "subject",
                "学科",
                _text(doc.subject or "未分类"),
                _text(result.get("subject") or "未分类"),
                "按正文关键词识别学科；低置信度仍保留为建议",
                confidence=float(after_facets.get("confidence") or 0.5),
            )
        )
    if (doc.material_type or "资料") != result.get("material_type"):
        changes.append(
            _change(
                "materialType",
                "meta",
                "materialType",
                "资料类型",
                _text(doc.material_type or "资料"),
                _text(result.get("material_type") or "资料"),
                "按文件名、正文和题目特征识别资料类型",
            )
        )
    if _facet_rows(before_facets) != _facet_rows(after_facets):
        changes.append(
            _change(
                "facets",
                "facets",
                "facets",
                "内容统计",
                _table(_facet_rows(before_facets)),
                _table(_facet_rows(after_facets)),
                "重新统计正文字数、公式、图片、表格和标题",
            )
        )
    before_summary = str(before_facets.get("summary") or "")
    after_summary = str(after_facets.get("summary") or "")
    if before_summary != after_summary:
        changes.append(
            _change(
                "summary",
                "facets",
                "summary",
                "整理摘要",
                _text(before_summary or "—"),
                _text(after_summary or "—"),
                "用正文首段生成便于识别的内容摘要",
            )
        )
    before_groups = before_facets.get("questionGroups") or []
    after_groups = after_facets.get("questionGroups") or []
    if before_groups != after_groups and after_groups:
        changes.append(
            _change(
                "questionGroups",
                "structure",
                "questionGroups",
                "题库结构",
                _list([
                    f"{g.get('name')} {g.get('count')} 题（第{g.get('first')}题起）"
                    for g in before_groups
                ]),
                _list([
                    f"{g.get('name')} {g.get('count')} 题（第{g.get('first')}题起）"
                    for g in after_groups
                ]),
                "按题型整理题库结构，点击题数可跳转",
            )
        )
    return changes


def _range_already_excluded(doc: RagDocument, start: int, end: int) -> bool:
    for item in doc.excluded_ranges or []:
        if not isinstance(item, dict):
            continue
        try:
            if int(item.get("start", -1)) <= start and int(item.get("end", -1)) >= end:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _structure_changes(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把确定性结构计划转成前端可勾选的 before/after 列表。"""
    changes: List[Dict[str, Any]] = []
    for spec in plan.get("changes") or []:
        changes.append(
            _change(
                str(spec.get("id") or ""),
                "structure",
                str(spec.get("field") or "reorderBlocks"),
                str(spec.get("label") or "结构整理"),
                _list(spec.get("before") or []),
                _list(spec.get("after") or []),
                str(spec.get("reason") or "按结构规则重排"),
                risk="medium",
                confidence=float(spec.get("confidence") or 0.85),
                extra={
                    "layout": spec.get("layout") or {},
                    "kind": spec.get("kind") or "reorder",
                },
            )
        )
    return changes


def _structure_suggestions(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    suggestions: List[Dict[str, Any]] = []
    for spec in plan.get("suggestions") or []:
        start, end = spec.get("start"), spec.get("end")
        if start is None or end is None:
            continue
        suggestions.append(
            _change(
                str(spec.get("id") or ""),
                "suggestion",
                "exclude",
                "建议剔除重复标题",
                _text(spec.get("text") or ""),
                _text("建议剔除"),
                str(spec.get("reason") or "重复标题"),
                risk="low",
                confidence=float(spec.get("confidence") or 0.85),
                action="exclude",
                extra={"range": {"start": start, "end": end, "kind": "text"}},
            )
        )
    return suggestions


def _layout_conflicts(changes: List[Dict[str, Any]], candidate: Dict[str, Any]) -> bool:
    """LLM 的移动项只要碰到确定性结构项的范围，就不展示，避免两份计划打架。"""
    candidate_ranges = layout_ranges(candidate.get("layout") or {})
    if not candidate_ranges:
        return False
    for change in changes:
        if change.get("field") not in {"reorderBlocks", "moveBlock", "headingLevel", "mergeSections"}:
            continue
        for start, end in layout_ranges(change.get("layout") or {}):
            for c_start, c_end in candidate_ranges:
                if c_start == c_end:
                    if start <= c_start < end:
                        return True
                elif start == end:
                    if c_start <= start < c_end:
                        return True
                elif c_start < end and c_end > start:
                    return True
    return False


def _deep_changes(doc: RagDocument, result: Dict[str, Any], options: Dict[str, Any], structure_plan: Optional[Dict[str, Any]] = None) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    changes = _structure_changes(structure_plan or {}) if options.get("structure", True) else []
    changes.extend(_quick_changes(doc, result))
    after_facets = result.get("facets") or {}
    groups = after_facets.get("questionGroups") or []
    before_groups = (doc.facets or {}).get("questionGroups") or []
    before_group_labels = [
        f"{g.get('name')} {g.get('count')} 题（第{g.get('first')}题起）" for g in before_groups
    ]
    after_group_labels = [
        f"{g.get('name')} {g.get('count')} 题（第{g.get('first')}题起）" for g in groups
    ]
    if (
        options.get("structure", True)
        and groups
        and before_group_labels != after_group_labels
        and not any(c.get("field") == "questionGroups" for c in changes)
    ):
        # 题库结构作为智能整理的一项；已经由基础分析包含时不重复。
        changes.append(
            _change(
                "deep:structure",
                "structure",
                "questionGroups",
                "识别题库结构",
                _list(before_group_labels),
                _list(after_group_labels),
                "识别题号与题型，只生成结构，不改题干和答案",
                confidence=0.86,
            )
        )
    image_suggestions: List[Dict[str, Any]] = []
    if options.get("imageLinking", True):
        links = image_links(doc.raw_content or "")
        existing_links = (doc.facets or {}).get("imageLinks") or []
        if links and links != existing_links:
            changes.append(
                _change(
                    "deep:imageLinks",
                    "image",
                    "imageLinks",
                    "图片关联",
                    _list(existing_links or ["未建立图片关联"]),
                    _list(links),
                    "按图片最近的题目/标题建立关联，保留原始图片",
                    confidence=0.8,
                )
            )
        for item in image_layout(doc.raw_content or ""):
            idx = int(item.get("index") or 0)
            url = str((doc.image_map or {}).get(str(idx)) or (doc.image_map or {}).get(idx) or "")
            label = item.get("label") or f"图{idx + 1}"
            if item.get("status") == "move":
                from_label = f"位于「{item.get('prevQuestion') or '文末'}」之后"
                to_label = f"移动到「{item.get('question') or '对应题目'}」"
                changes.append(
                    _change(
                        f"imageMove:{idx}:move",
                        "image",
                        "imageMove",
                        f"{label} 位置纠正",
                        _image_value(label, url, from_label),
                        _image_value(label, url, to_label),
                        item.get("reason") or "图片有明确题目指向，移动到对应题目附近",
                        confidence=0.78,
                        extra={
                            "kind": "image",
                            "imageUrl": url,
                            "imageIndex": idx,
                            "targetText": item.get("question") or "",
                            "source": {"start": item["start"], "end": item["end"]},
                            "target": {"start": item["questionStart"], "end": item["questionEnd"]},
                        },
                    )
                )
            elif item.get("status") == "irrelevant":
                image_suggestions.append(
                    _change(
                        f"exclude:image:{idx}",
                        "image",
                        "excludeImage",
                        f"建议剔除无关图片 {label}",
                        _image_value(label, url, item.get("reason") or "找不到归属题目"),
                        _text("建议剔除"),
                        item.get("reason") or "图片找不到归属题目",
                        risk="medium",
                        confidence=0.7,
                        selectable=True,
                        action="exclude",
                        extra={
                            "kind": "image",
                            "imageUrl": url,
                            "imageIndex": idx,
                            "range": {"start": item["start"], "end": item["end"], "kind": "image"},
                        },
                    )
                )
    suggestions: List[Dict[str, Any]] = []
    if options.get("structure", True):
        suggestions.extend(_structure_suggestions(structure_plan or {}))
    suggestions.extend(image_suggestions)
    if options.get("duplicateDetection", True):
        for idx, item in enumerate(duplicate_blocks(doc.raw_content or "", doc.content_structure)):
            if _range_already_excluded(doc, item["start"], item["end"]):
                continue
            suggestions.append(
                _change(
                    f"exclude:duplicate:{idx}",
                    "suggestion",
                    "exclude",
                    "建议剔除重复内容",
                    _text(item.get("text") or "重复段落"),
                    _text("建议剔除"),
                    item.get("reason") or "重复段落",
                    risk="medium",
                    confidence=0.8,
                    selectable=True,
                    action="exclude",
                    extra={"range": {"start": item["start"], "end": item["end"], "kind": item.get("kind", "text")}},
                )
            )
    if options.get("cleanupSuggestions", True):
        for idx, item in enumerate(noise_blocks(doc.raw_content or "", doc.content_structure)):
            if _range_already_excluded(doc, item["start"], item["end"]):
                continue
            suggestions.append(
                _change(
                    f"exclude:noise:{idx}",
                    "suggestion",
                    "exclude",
                    "建议剔除噪声",
                    _text(item.get("text") or "页码/页眉页脚"),
                    _text("建议剔除"),
                    item.get("reason") or "疑似页码/页眉页脚",
                    risk="medium",
                    confidence=0.72,
                    selectable=True,
                    action="exclude",
                    extra={"range": {"start": item["start"], "end": item["end"], "kind": item.get("kind", "text")}},
                )
            )
        for idx, item in enumerate(garbage_blocks(doc.raw_content or "", doc.material_type, doc.content_structure)):
            if _range_already_excluded(doc, item["start"], item["end"]):
                continue
            suggestions.append(
                _change(
                    f"exclude:garbage:{idx}",
                    "suggestion",
                    "exclude",
                    "建议剔除无关文字",
                    _text(item.get("text") or "无关文字"),
                    _text("建议剔除"),
                    item.get("reason") or "疑似无关短文本",
                    risk="medium",
                    confidence=0.68,
                    selectable=True,
                    action="exclude",
                    extra={"range": {"start": item["start"], "end": item["end"], "kind": item.get("kind", "text")}},
                )
            )
        for idx, item in enumerate(off_topic_blocks(doc.raw_content or "", doc.content_structure)):
            if _range_already_excluded(doc, item["start"], item["end"]):
                continue
            suggestions.append(
                _change(
                    f"exclude:offtopic:{idx}",
                    "suggestion",
                    "exclude",
                    "建议剔除无关日常内容",
                    _text(item.get("text") or "无关日常内容"),
                    _text("建议剔除"),
                    item.get("reason") or "与上下文无关",
                    risk="medium",
                    confidence=0.72,
                    selectable=True,
                    action="exclude",
                    extra={"range": {"start": item["start"], "end": item["end"], "kind": "text"}},
                )
            )
    return changes, suggestions


def _blocks_for_llm(text: str, structure: Optional[list] = None) -> List[Dict[str, Any]]:
    """给 LLM 的块清单：限制条数和单块长度，避免把整篇长文塞进上下文。"""
    blocks = build_blocks(text or "", structure)
    selected: List[Dict[str, Any]] = []
    total = 0
    for block in blocks:
        if len(selected) >= 240 or total >= 30000:
            break
        item = dict(block)
        original_text = str(item.get("text") or "")
        item["fullText"] = original_text
        item["text"] = original_text[:1200]
        total += len(item["text"])
        selected.append(item)
    return selected


def _images_for_llm(doc: RagDocument, limit: int = 20) -> List[Dict[str, Any]]:
    """把文档图片读成 data URL，供多模态整理模型直接看。

    只发送正文里仍存在【图N】标记的图片，且最多 12 张，避免一次请求
    把上下文/带宽打满；图片读取失败则跳过，不阻断纯文本整理。
    """
    from app.services.ai.chat_engine import stored_image_to_data_url

    raw = doc.raw_content or ""
    present = {
        int(match.group(1)): match.start()
        for match in re.finditer(r"【图(\d+)】", raw)
    }
    items: List[Dict[str, Any]] = []
    for key, url in (doc.image_map or {}).items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        if index not in present:
            continue
        data_url = stored_image_to_data_url(str(url or ""))
        if not data_url:
            continue
        items.append(
            {
                "index": index,
                "label": f"图{index}",
                "url": data_url,
                "position": present[index],
            }
        )
    items.sort(key=lambda item: item["position"])
    return items[:limit]


def _image_manifest(images: List[Dict[str, Any]]) -> str:
    if not images:
        return ""
    lines = ["以下图片随消息附在文字之后；编号与正文中的【图N】标记一一对应："]
    lines.extend(f"- 【{item['label']}】" for item in images)
    return "\n".join(lines)


def _parse_llm_object(content: str) -> Dict[str, Any]:
    """解析 LLM 的 JSON；容忍围栏、尾随逗号和 LaTeX 反斜杠。"""
    from app.services.ai.agent import json_repair

    source = json_repair.clean(content or "")
    candidates = [
        source,
        json_repair.collapse_backslashes(source),
        json_repair.repair(source),
        json_repair.repair(json_repair.collapse_backslashes(source)),
    ]
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except Exception:  # noqa: BLE001 - 继续尝试下一种修复
            continue
        if isinstance(data, dict):
            return data
    return {}


async def _run_llm_plan(
    db: AsyncSession,
    doc: RagDocument,
    plan: MaterialOrganizePlan,
    blocks: List[Dict[str, Any]],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    """调用真正的多模态整理模型；失败不阻断确定性结构整理，但把原因原样记下来。"""
    from app.services.ai.base_client import ChatMessage, ImageBlock, TextBlock
    from app.services.ai.db_config import chat_with_config
    from app.services.material_organize_contract import (
        build_llm_messages,
        normalize_llm_ops,
        validate_llm_plan,
    )

    images = _images_for_llm(doc)
    messages = build_llm_messages(
        doc.id,
        doc.file_name or "",
        plan.base_revision or "",
        blocks,
        options or {},
        image_manifest=_image_manifest(images),
    )
    chat_messages: List[ChatMessage] = []
    for item in messages:
        if item["role"] == "user" and images:
            content: List[Any] = [TextBlock(type="text", text=item["content"])]
            for image in images:
                content.append(TextBlock(type="text", text=f"【{image['label']}】"))
                content.append(
                    ImageBlock(type="image_url", image_url={"url": image["url"]})
                )
            chat_messages.append(ChatMessage(role="user", content=content))
        else:
            chat_messages.append(ChatMessage(role=item["role"], content=item["content"]))
    try:
        response = await asyncio.wait_for(
            chat_with_config(
                db,
                chat_messages,
                model="deepseek-flash" if images else None,
                user_id=doc.user_id,
                temperature=0.1,
                max_tokens=6000,
            ),
            timeout=90,
        )
        data = _parse_llm_object(response.content or "")
        if not data:
            return {"used": True, "valid": False, "ops": [], "errors": ["模型没有返回合法 JSON"]}
        data = normalize_llm_ops(blocks, data)
        validated = validate_llm_plan(doc.id, plan.base_revision or "", blocks, data)
        return {
            "used": True,
            "valid": bool(validated.get("ok")),
            "ops": validated.get("ops") or [],
            "errors": validated.get("errors") or [],
            "images": len(images),
        }
    except Exception as exc:  # noqa: BLE001 - 模型不可用/超时不能让整个整理失败
        return {
            "used": False,
            "valid": False,
            "ops": [],
            "errors": [str(exc)[:300]],
            "images": len(images),
        }


def _llm_change_specs(
    doc: RagDocument, blocks: List[Dict[str, Any]], ops: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """把通过白名单校验的 LLM ops 转成预览项；不改正文以外的任何东西。"""
    by_id = {str(block.get("id")): block for block in blocks}
    changes: List[Dict[str, Any]] = []
    suggestions: List[Dict[str, Any]] = []
    attach_links: List[str] = []
    existing_links = list((doc.facets or {}).get("imageLinks") or [])

    for index, op in enumerate(ops):
        name = str(op.get("op") or "")
        target_id = str(op.get("target") or "")
        block = by_id.get(target_id)
        reason = str(op.get("reason") or "模型判断")
        try:
            confidence = float(op.get("confidence") or 0.6)
        except (TypeError, ValueError):
            confidence = 0.6

        if name == "rename_file":
            value = str(op.get("value") or "").strip()
            if value:
                changes.append(
                    _change(
                        f"llm:rename:{index}", "meta", "fileName", "文件名（AI 建议）",
                        _text(doc.file_name or ""), _text(value), reason,
                        confidence=confidence,
                    )
                )
        elif name == "set_subject":
            value = str(op.get("value") or "").strip()
            if value:
                changes.append(
                    _change(
                        f"llm:subject:{index}", "meta", "subject", "学科（AI 建议）",
                        _text(doc.subject or "未分类"), _text(value), reason,
                        confidence=confidence,
                    )
                )
        elif name == "set_material_type":
            value = str(op.get("value") or "").strip()
            if value:
                changes.append(
                    _change(
                        f"llm:type:{index}", "meta", "materialType", "资料类型（AI 建议）",
                        _text(doc.material_type or "资料"), _text(value), reason,
                        confidence=confidence,
                    )
                )
        elif name == "suggest_exclude" and block:
            # 多模态模型已经看过图片；低置信度图片仍只保留确定性规则的建议。
            if block.get("kind") == "image" and confidence < 0.7:
                continue
            extra = {
                "range": {
                    "start": int(block["start"]),
                    "end": int(block["end"]),
                    "kind": block.get("kind") or "text",
                }
            }
            if block.get("kind") == "image":
                marker = re.search(r"【图(\d+)】", block.get("text") or "")
                if marker:
                    image_index = int(marker.group(1))
                    extra["kind"] = "image"
                    extra["imageIndex"] = image_index
                    extra["imageUrl"] = str(
                        (doc.image_map or {}).get(str(image_index))
                        or (doc.image_map or {}).get(image_index)
                        or ""
                    )
            suggestions.append(
                _change(
                    f"llm:exclude:{index}", "suggestion", "exclude", "模型建议剔除",
                    _text(block.get("text") or ""), _text("建议剔除"), reason,
                    risk="medium", confidence=confidence, action="exclude",
                    extra=extra,
                )
            )
        elif name == "move_block" and block:
            anchor = by_id.get(str(op.get("anchor") or ""))
            if not anchor:
                continue
            position = "after" if str(op.get("position") or "before") == "after" else "before"
            changes.append(
                _change(
                    f"llm:move:{index}", "structure", "moveBlock", "块位置调整（AI 建议）",
                    _list([f"「{_short(block.get('text') or '', 40)}」当前位置"]),
                    _list([f"移动到「{_short(anchor.get('text') or '', 40)}」{position}"]),
                    reason,
                    risk="medium",
                    confidence=confidence,
                    extra={
                        "layout": {
                            "move": {
                                "source": {"start": int(block["start"]), "end": int(block["end"])},
                                "target": {"start": int(anchor["start"]), "end": int(anchor["end"])},
                                "position": position,
                            }
                        },
                        "kind": "move",
                    },
                )
            )
        elif name == "reorder_blocks":
            order_ids = [str(item) for item in (op.get("blocks") or [])]
            ordered = [by_id.get(item) for item in order_ids]
            if len(ordered) < 2 or any(item is None for item in ordered):
                continue
            slots = sorted(ordered, key=lambda item: int(item["start"]))
            changes.append(
                _change(
                    f"llm:reorder:{index}", "structure", "reorderBlocks", "块顺序调整（AI 建议）",
                    _list([_short(item.get("text") or "", 40) for item in slots]),
                    _list([_short(item.get("text") or "", 40) for item in ordered]),
                    reason,
                    risk="medium",
                    confidence=confidence,
                    extra={
                        "layout": {
                            "slots": [
                                {"start": int(item["start"]), "end": int(item["end"])}
                                for item in slots
                            ],
                            "texts": [
                                str(item.get("fullText") or item.get("text") or "")
                                for item in ordered
                            ],
                        },
                        "kind": "reorder",
                    },
                )
            )
        elif name == "set_heading_level" and block:
            try:
                level = max(1, min(6, int(op.get("level") or 2)))
            except (TypeError, ValueError):
                continue
            current = str(block.get("fullText") or block.get("text") or "")
            bare = re.sub(r"^\s*#{1,6}\s*", "", current)
            new_text = "#" * level + " " + bare
            changes.append(
                _change(
                    f"llm:heading:{index}", "structure", "headingLevel", "标题层级（AI 建议）",
                    _text(current), _text(new_text), reason,
                    confidence=confidence,
                    extra={
                        "layout": {
                            "slots": [
                                {"start": int(block["start"]), "end": int(block["end"])}
                            ],
                            "texts": [new_text],
                        },
                        "kind": "reorder",
                    },
                )
            )
        elif name == "attach_image" and block:
            anchor = by_id.get(str(op.get("anchor") or ""))
            if not anchor:
                continue
            match = re.search(r"【图(\d+)】", block.get("text") or "")
            label = f"图{int(match.group(1)) + 1}" if match else "图片"
            visual_reason = _short(reason, 28)
            attach_links.append(
                f"{label} → {_short(anchor.get('text') or '', 36)}"
                + (f"（{visual_reason}）" if visual_reason else "")
            )
        elif name == "merge_sections" and block:
            changes.append(
                _change(
                    f"llm:merge:{index}", "structure", "mergeSections", "合并章节（AI 建议）",
                    _text(block.get("text") or ""),
                    _text("并入上一节，删除重复标题"),
                    reason,
                    confidence=confidence,
                    extra={
                        "layout": {
                            "slots": [{"start": int(block["start"]), "end": int(block["end"])}],
                            "texts": [""],
                        },
                        "kind": "reorder",
                    },
                )
            )

    if attach_links:
        new_links = existing_links + [link for link in attach_links if link not in existing_links]
        changes.append(
            _change(
                "llm:imageLinks", "image", "imageLinks", "图片关联（AI 建议）",
                _list(existing_links or ["未建立图片关联"]),
                _list(new_links),
                "模型根据图片位置和上下文建议关联",
                confidence=0.7,
                extra={"kind": "image"},
            )
        )
    return changes, suggestions


def _short(value: str, limit: int = 56) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _plan_payload(plan: MaterialOrganizePlan) -> Dict[str, Any]:
    data = plan.plan_json or {}
    return {
        "planId": plan.id,
        "docId": plan.doc_id,
        "mode": plan.mode,
        "status": plan.status,
        "stage": plan.stage,
        "progress": plan.progress,
        "summary": plan.summary_json or data.get("summary") or {},
        "changes": data.get("changes", []),
        "suggestions": data.get("suggestions", []),
        "appliedChangeIds": data.get("appliedChangeIds") or [],
        "appliedExclusionIds": data.get("appliedExclusionIds") or [],
        "baseRevision": plan.base_revision,
        "error": plan.error_msg or "",
    }


DISPLAY_TZ = timezone(timedelta(hours=8))


def _format_display_time(value: Optional[datetime]) -> str:
    """整理记录统一按 Asia/Shanghai 展示。

    数据库 `func.now()` 使用 UTC（PG 默认），而页面用户在中国时区；
    不能在接口里直接 strftime，否则会出现“凌晨 3 点”的假时间。
    """
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(DISPLAY_TZ).strftime("%Y-%m-%d %H:%M")


async def list_plans(
    db: AsyncSession, user_id: int, limit: int = 30
) -> List[Dict[str, Any]]:
    rows = (
        await db.execute(
            select(MaterialOrganizePlan, RagDocument.file_name)
            .join(RagDocument, RagDocument.id == MaterialOrganizePlan.doc_id)
            .where(MaterialOrganizePlan.user_id == user_id)
            .order_by(MaterialOrganizePlan.create_time.desc(), MaterialOrganizePlan.id.desc())
            .limit(max(1, min(limit, 100)))
        )
    ).all()
    out = []
    plan_batch_ids = set()
    for plan, file_name in rows:
        plan_batch_ids.add(str(plan.id))
        summary = plan.summary_json or (plan.plan_json or {}).get("summary") or {}
        plan_data = plan.plan_json or {}
        applied_change_ids = plan_data.get("appliedChangeIds")
        applied_exclusion_ids = plan_data.get("appliedExclusionIds")
        changed = int(summary.get("changed") or 0)
        suggestion_count = int(summary.get("suggestions") or 0)
        if plan.status == "applied" and isinstance(applied_change_ids, list):
            # 内容统计是派生数据，不算用户确认的业务变更。
            facet_ids = {
                c.get("id") for c in (plan_data.get("changes") or []) if c.get("field") == "facets"
            }
            changed = len([cid for cid in applied_change_ids if cid not in facet_ids])
            suggestion_count = len(applied_exclusion_ids or [])
        out.append(
            {
                "planId": plan.id,
                "docId": plan.doc_id,
                "docName": file_name or "未命名资料",
                "mode": plan.mode,
                "status": plan.status,
                "stage": plan.stage,
                "progress": plan.progress,
                "changed": changed,
                "suggestions": suggestion_count,
                "error": plan.error_msg or "",
                "legacy": False,
                "createTime": _format_display_time(plan.create_time),
            }
        )

    # 兼容旧版智能整理日志：旧记录没有 plan 表，但同样应该出现在“整理记录”里。
    legacy_rows = (
        await db.execute(
            select(MaterialOrganizeLog, RagDocument.file_name)
            .join(RagDocument, RagDocument.id == MaterialOrganizeLog.doc_id)
            .where(
                MaterialOrganizeLog.user_id == user_id,
                ~MaterialOrganizeLog.batch_id.like("version:%"),
            )
            .order_by(MaterialOrganizeLog.create_time.desc(), MaterialOrganizeLog.id.desc())
            .limit(max(1, min(limit, 100)))
        )
    ).all()
    for log, file_name in legacy_rows:
        if str(log.batch_id) in plan_batch_ids:
            continue
        before = log.before_json or {}
        after = log.after_json or {}
        changed = sum(1 for key in set(before) | set(after) if before.get(key) != after.get(key))
        out.append(
            {
                "planId": -int(log.id),
                "docId": log.doc_id,
                "docName": file_name or "未命名资料",
                "mode": "legacy",
                "status": "rolled_back" if log.undone_at else "applied",
                "stage": "done",
                "progress": 100,
                "changed": changed,
                "suggestions": 0,
                "error": "",
                "legacy": True,
                "createTime": _format_display_time(log.create_time),
            }
        )
    out.sort(key=lambda item: item.get("createTime") or "", reverse=True)
    return out[: max(1, min(limit, 100))]


def _legacy_payload(log: MaterialOrganizeLog, file_name: str = "") -> Dict[str, Any]:
    """旧版整理日志只存了字段快照，没有 plan_json；仍尽量还原可比对字段。"""
    before = log.before_json or {}
    after = log.after_json or {}
    changes: List[Dict[str, Any]] = []
    labels = {
        "fileName": ("文件名", "meta"),
        "subject": ("学科", "meta"),
        "materialType": ("资料类型", "meta"),
    }
    for field, (label, group) in labels.items():
        a, b = str(before.get(field) or ""), str(after.get(field) or "")
        if a != b:
            changes.append(
                _change(
                    f"legacy:{field}", group, field, label, _text(a or "—"), _text(b or "—"),
                    "旧版整理快照", selectable=False
                )
            )
    before_facets = before.get("facets") or {}
    after_facets = after.get("facets") or {}
    stats = [
        ("词数", "wordCount"),
        ("公式", "formulaCount"),
        ("图片", "imageCount"),
        ("表格", "tableCount"),
        ("标题", "headingCount"),
    ]
    rows_before = [[label, str(before_facets.get(key) or 0)] for label, key in stats]
    rows_after = [[label, str(after_facets.get(key) or 0)] for label, key in stats]
    if rows_before != rows_after:
        changes.append(
            _change(
                "legacy:facets", "facets", "facets", "内容统计",
                _table(rows_before), _table(rows_after), "旧版整理快照", selectable=False
            )
        )
    return {
        "planId": -int(log.id),
        "docId": log.doc_id,
        "docName": file_name,
        "mode": "legacy",
        "status": "rolled_back" if log.undone_at else "applied",
        "stage": "done",
        "progress": 100,
        "summary": {"changed": len(changes), "suggestions": 0},
        "changes": changes,
        "suggestions": [],
        "error": "",
        "legacy": True,
    }


async def get_legacy_record(db: AsyncSession, user_id: int, record_id: int) -> Dict[str, Any]:
    row = (
        await db.execute(
            select(MaterialOrganizeLog, RagDocument.file_name)
            .join(RagDocument, RagDocument.id == MaterialOrganizeLog.doc_id)
            .where(
                MaterialOrganizeLog.id == -record_id,
                MaterialOrganizeLog.user_id == user_id,
                ~MaterialOrganizeLog.batch_id.like("version:%"),
            )
        )
    ).first()
    if not row:
        raise ValueError("整理记录不存在")
    log, file_name = row
    return _legacy_payload(log, file_name or "")


async def delete_plan_record(db: AsyncSession, user_id: int, record_id: int) -> Dict[str, Any]:
    """删除一条整理记录。

    · 正数 = MaterialOrganizePlan；同时清掉该计划的旧版日志（batch_id）
    · 负数 = 旧版 MaterialOrganizeLog（planId 的负数编码）
    · 只删记录，不回退已经应用的文档变更；文档本身不变
    """
    if record_id < 0:
        log_id = -record_id
        row = (
            await db.execute(
                select(MaterialOrganizeLog).where(
                    MaterialOrganizeLog.id == log_id,
                    MaterialOrganizeLog.user_id == user_id,
                    ~MaterialOrganizeLog.batch_id.like("version:%"),
                )
            )
        ).scalars().first()
        if not row:
            raise ValueError("整理记录不存在或无权删除")
        await db.delete(row)
        await db.commit()
        return {"recordId": record_id, "deleted": True, "kind": "legacy"}

    plan = await get_plan(db, user_id, record_id)
    await db.execute(
        delete(MaterialOrganizeLog).where(
            MaterialOrganizeLog.batch_id == str(plan.id),
            MaterialOrganizeLog.user_id == user_id,
        )
    )
    await db.delete(plan)
    await db.commit()
    return {"recordId": record_id, "deleted": True, "kind": "plan"}


async def _get_doc_for_user(db: AsyncSession, user_id: int, doc_id: int) -> RagDocument:
    from app.services.rag.rag_write_service import get_document

    return await get_document(db, user_id, doc_id)


async def create_deep_plan(
    db: AsyncSession, user_id: int, doc_id: int, options: Dict[str, Any]
) -> Dict[str, Any]:
    doc = await _get_doc_for_user(db, user_id, doc_id)
    plan = MaterialOrganizePlan(
        user_id=user_id,
        doc_id=doc.id,
        mode="deep",
        status="running",
        stage="blocks",
        progress=5,
        base_revision=_doc_revision(doc),
        options_json=options,
        plan_json={},
        summary_json={"changed": 0, "suggestions": 0, "mode": "deep"},
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return _plan_payload(plan)


async def process_deep_plan(plan_id: int) -> None:
    """后台执行深度整理；阶段写库，前端可实时读取。"""
    async with async_session_factory() as db:
        plan = (
            await db.execute(select(MaterialOrganizePlan).where(MaterialOrganizePlan.id == plan_id))
        ).scalar_one_or_none()
        if not plan:
            return
        try:
            plan.stage = "structure"
            plan.progress = 15
            plan.update_time = datetime.now()
            await db.commit()
            doc = (
                await db.execute(select(RagDocument).where(RagDocument.id == plan.doc_id))
            ).scalar_one_or_none()
            if not doc:
                raise ValueError("文档不存在")

            # 1) 确定性结构：编号、题目/答案、表格行、章节顺序。先做，保证即使
            #    模型不可用也能给出可解释、可回退的结构整理建议。
            structure_plan = build_structure_plan(doc.raw_content or "", doc.content_structure)
            plan.progress = 35
            plan.update_time = datetime.now()
            await db.commit()

            # 2) 真正的模型语义整理：读取块清单，只接受结构化 ops，服务端白名单校验。
            llm_blocks = _blocks_for_llm(doc.raw_content or "", doc.content_structure)
            options = plan.options_json or {}
            llm_meta = await _run_llm_plan(db, doc, plan, llm_blocks, options)
            plan.stage = "images"
            plan.progress = 58
            plan.update_time = datetime.now()
            await db.commit()

            result = analyze_material(
                doc.file_name or "",
                doc.raw_content or "",
                None,
                len(doc.image_map or {}),
            )
            changes, suggestions = _deep_changes(doc, result, options, structure_plan)
            llm_changes, llm_suggestions = _llm_change_specs(doc, llm_blocks, llm_meta.get("ops") or [])

            # 规则已经给出的元信息项不重复展示；结构项允许多条（编号/表格各一条）。
            existing_meta_fields = {
                str(change.get("field"))
                for change in changes
                if change.get("field") in {"fileName", "subject", "materialType"}
            }
            # 图片关联是“规则 + 视觉识别”共同结果，合并到同一条变更，避免两个
            # imageLinks 变更互相覆盖。
            llm_links_change = next(
                (change for change in llm_changes if change.get("field") == "imageLinks"),
                None,
            )
            if llm_links_change:
                existing_links_change = next(
                    (change for change in changes if change.get("field") == "imageLinks"),
                    None,
                )
                if existing_links_change:
                    merged = list((existing_links_change.get("after") or {}).get("value") or [])
                    for link in (llm_links_change.get("after") or {}).get("value") or []:
                        label = str(link).split("→", 1)[0].strip()
                        # 同一张图优先保留模型给出的语义/位置说明，避免同一图出现两条。
                        merged = [old for old in merged if not str(old).startswith(label + " →")]
                        if link not in merged:
                            merged.append(link)
                    existing_links_change["after"] = _list(merged)
                    existing_links_change["reason"] = (
                        str(existing_links_change.get("reason") or "按图片位置建立关联")
                        + "；并结合模型对图片内容的理解补充关联"
                    )
                    llm_changes = [change for change in llm_changes if change is not llm_links_change]
                else:
                    existing_meta_fields.discard("imageLinks")

            has_deterministic_structure = bool((structure_plan or {}).get("changes"))
            for change in llm_changes:
                if change.get("field") in existing_meta_fields:
                    continue
                if change.get("field") in {"reorderBlocks", "moveBlock", "headingLevel", "mergeSections"}:
                    # 服务端已经识别出确定的编号/题目/章节结构时，模型不再重复
                    # 提结构操作，避免两套顺序互相覆盖。
                    if has_deterministic_structure or _layout_conflicts(changes, change):
                        continue
                changes.append(change)
            existing_ranges = {
                (int((item.get("range") or {}).get("start", -1)), int((item.get("range") or {}).get("end", -1)))
                for item in suggestions
            }
            for suggestion in llm_suggestions:
                rng = suggestion.get("range") or {}
                key = (int(rng.get("start", -1)), int(rng.get("end", -1)))
                if key in existing_ranges:
                    continue
                existing_ranges.add(key)
                suggestions.append(suggestion)

            plan.stage = "preview"
            plan.progress = 86
            plan.update_time = datetime.now()
            await db.commit()
            plan.plan_json = {
                "before": _doc_snapshot(doc),
                "after": {
                    "fileName": result.get("display_name") or doc.file_name,
                    "subject": result.get("subject") or doc.subject,
                    "materialType": result.get("material_type") or doc.material_type,
                    "facets": result.get("facets") or doc.facets,
                },
                "changes": changes,
                "suggestions": suggestions,
                "llm": llm_meta,
            }
            plan.summary_json = {
                "changed": len(changes),
                "suggestions": len(suggestions),
                "mode": "deep",
                "llmUsed": bool(llm_meta.get("used")),
                "llmValid": bool(llm_meta.get("valid")),
                "llmOps": len(llm_meta.get("ops") or []),
                "llmImages": int(llm_meta.get("images") or 0),
            }
            plan.status = "ready"
            plan.stage = "done"
            plan.progress = 100
            plan.error_msg = None
            plan.update_time = datetime.now()
            await db.commit()
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            plan.status = "failed"
            plan.stage = "failed"
            plan.error_msg = str(e)[:500]
            plan.update_time = datetime.now()
            await db.commit()


async def get_plan(db: AsyncSession, user_id: int, plan_id: int) -> MaterialOrganizePlan:
    plan = (
        await db.execute(
            select(MaterialOrganizePlan).where(
                MaterialOrganizePlan.id == plan_id,
                MaterialOrganizePlan.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if not plan:
        raise ValueError("整理计划不存在或无权访问")
    return plan


async def apply_plan(
    db: AsyncSession,
    user_id: int,
    plan_id: int,
    change_ids: Optional[List[str]] = None,
    exclusion_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    plan = await get_plan(db, user_id, plan_id)
    if plan.status != "ready":
        raise ValueError("整理计划尚未完成，不能应用")
    doc = await _get_doc_for_user(db, user_id, plan.doc_id)
    if _doc_revision(doc) != plan.base_revision:
        raise ValueError("文档在预览后发生了变化，请重新整理")
    data = plan.plan_json or {}
    changes = data.get("changes") or []
    suggestions = data.get("suggestions") or []
    # AI/结构建议默认不勾选：调用方必须明确传入要应用的 changeIds。
    selected = set(change_ids or [])
    selected_exclusions = set(exclusion_ids or [])
    if not selected and not selected_exclusions:
        raise ValueError("没有选择要应用的整理项")
    before = _doc_snapshot(doc)
    applied = []
    image_moves: List[Dict[str, Any]] = []
    layout_ops: List[Dict[str, Any]] = []

    for change in changes:
        if change.get("id") not in selected:
            continue
        field = change.get("field")
        after = change.get("after") or {}
        value = after.get("value")
        if field in {"reorderBlocks", "moveBlock", "headingLevel", "mergeSections"}:
            layout = change.get("layout") or {}
            if layout:
                layout_ops.append(layout)
            applied.append(change.get("id"))
            continue
        if field == "imageMove":
            image_moves.append(change)
            applied.append(change.get("id"))
            continue
        if field == "fileName" and value:
            doc.original_file_name = doc.original_file_name or doc.file_name
            doc.file_name = str(value)
        elif field == "subject":
            doc.subject = str(value or "")
        elif field == "materialType":
            doc.material_type = str(value or "")
        elif field == "facets":
            doc.facets = data.get("after", {}).get("facets") or doc.facets
        elif field == "summary":
            facets = dict(doc.facets or {})
            facets["summary"] = str(value or "")
            doc.facets = facets
        elif field == "questionGroups":
            facets = dict(doc.facets or {})
            facets["questionGroups"] = data.get("after", {}).get("facets", {}).get("questionGroups", [])
            doc.facets = facets
        elif field == "imageLinks":
            facets = dict(doc.facets or {})
            facets["imageLinks"] = after.get("value") or []
            doc.facets = facets
        applied.append(change.get("id"))

    selected_ranges = []
    for suggestion in suggestions:
        if suggestion.get("id") not in selected_exclusions:
            continue
        rng = suggestion.get("range") or {}
        if rng.get("start") is None or rng.get("end") is None:
            continue
        selected_ranges.append(
            {
                "start": int(rng["start"]),
                "end": int(rng["end"]),
                "kind": rng.get("kind", "text"),
                "reason": suggestion.get("reason") or "用户确认剔除",
                "planId": str(plan.id),
            }
        )
    # 旧的软剔除范围也基于旧偏移；重排后按“剔除文本”重新定位，找不到就丢弃，
    # 绝不能把旧偏移直接套到新正文上（那会误删别的内容）。
    raw_before_layout = doc.raw_content or ""
    range_snapshots: List[Tuple[Dict[str, Any], str]] = []
    for item in list(doc.excluded_ranges or []) + selected_ranges:
        try:
            start, end = int(item.get("start", -1)), int(item.get("end", -1))
        except (TypeError, ValueError):
            continue
        if 0 <= start < end <= len(raw_before_layout):
            range_snapshots.append((dict(item), raw_before_layout[start:end]))
    if selected_ranges and not (layout_ops or image_moves):
        doc.excluded_ranges = list(doc.excluded_ranges or []) + selected_ranges

    if layout_ops:
        doc.raw_content = apply_layouts(doc.raw_content or "", layout_ops)
        doc.content_structure = _rebuild_content_structure(doc.raw_content or "")

    if image_moves:
        raw = doc.raw_content or ""
        for change in sorted(
            image_moves, key=lambda item: int((item.get("source") or {}).get("start", 0)), reverse=True
        ):
            try:
                index = int(change.get("imageIndex"))
            except (TypeError, ValueError):
                continue
            marker = f"【图{index}】"
            marker_match = re.search(r"(?m)^" + re.escape(marker) + r"\s*$", raw)
            if not marker_match:
                continue
            target_text = str(change.get("targetText") or "").strip()
            if not target_text:
                continue
            target_match = None
            for candidate in re.finditer(r"(?m)^.*" + re.escape(target_text[:24]) + r".*$", raw):
                if marker not in candidate.group(0):
                    target_match = candidate
                    break
            if not target_match:
                continue
            target_pos = target_match.start()
            raw = raw[: marker_match.start()] + raw[marker_match.end() :]
            if target_pos > marker_match.end():
                target_pos -= marker_match.end() - marker_match.start()
            target_pos = max(0, min(target_pos, len(raw)))
            raw = raw[:target_pos] + marker + "\n" + raw[target_pos:]
        doc.raw_content = raw
        doc.content_structure = _rebuild_content_structure(raw)

    if (layout_ops or image_moves) and range_snapshots:
        remapped_ranges = []
        for item, text in range_snapshots:
            if not text:
                continue
            raw_now = doc.raw_content or ""
            positions = [match.start() for match in re.finditer(re.escape(text), raw_now)]
            if not positions:
                continue
            original_start = int(item.get("start", 0))
            position = min(positions, key=lambda value: abs(value - original_start))
            item["start"] = position
            item["end"] = position + len(text)
            remapped_ranges.append(item)
        doc.excluded_ranges = remapped_ranges

    if layout_ops or image_moves:
        # 重排后重新统计题库结构/字数等派生数据，避免 facets 还停留在旧顺序。
        try:
            refreshed = analyze_material(
                doc.file_name or "",
                doc.raw_content or "",
                None,
                len(doc.image_map or {}),
            )
            facets = dict(doc.facets or {})
            for key in (
                "wordCount",
                "formulaCount",
                "imageCount",
                "tableCount",
                "headingCount",
                "questionGroups",
                "summary",
            ):
                if key in (refreshed.get("facets") or {}):
                    facets[key] = refreshed["facets"][key]
            doc.facets = facets
        except Exception:  # noqa: BLE001 - 统计失败不影响正文变更
            pass

    after = _doc_snapshot(doc)
    # 记录用户真正确认的变更，而不是把整份预览当成“已应用”。
    data = dict(data)
    data["appliedChangeIds"] = list(selected)
    data["appliedExclusionIds"] = list(selected_exclusions)
    plan.plan_json = data
    db.add(
        MaterialOrganizeLog(
            user_id=user_id,
            batch_id=str(plan.id),
            doc_id=doc.id,
            before_json=before,
            after_json=after,
        )
    )
    plan.status = "applied"
    plan.stage = "done"
    plan.progress = 100
    plan.update_time = datetime.now()
    await db.commit()
    return {
        "planId": plan.id,
        "docId": doc.id,
        "applied": applied,
        "excluded": len(selected_ranges),
        "needsReindex": bool(selected_ranges or image_moves or layout_ops),
        "changes": data.get("changes", []),
    }


async def rollback_plan(db: AsyncSession, user_id: int, plan_id: int) -> Dict[str, Any]:
    log = (
        await db.execute(
            select(MaterialOrganizeLog).where(
                MaterialOrganizeLog.user_id == user_id,
                MaterialOrganizeLog.batch_id == str(plan_id),
                MaterialOrganizeLog.undone_at.is_(None),
            )
        )
    ).scalars().first()
    if not log or not log.before_json:
        raise ValueError("没有可回退的整理记录")
    doc = await _get_doc_for_user(db, user_id, log.doc_id)
    before = log.before_json
    previous_raw = doc.raw_content or ""
    doc.file_name = before.get("fileName") or doc.file_name
    doc.original_file_name = before.get("originalFileName") or doc.original_file_name
    doc.subject = before.get("subject") or None
    doc.material_type = before.get("materialType") or None
    doc.facets = before.get("facets") or None
    doc.excluded_ranges = before.get("excludedRanges") or []
    if before.get("rawContent") is not None:
        doc.raw_content = before.get("rawContent") or ""
    if "contentStructure" in before:
        doc.content_structure = before.get("contentStructure") or []
    log.undone_at = datetime.now()
    plan = await get_plan(db, user_id, plan_id)
    plan.status = "rolled_back"
    plan.update_time = datetime.now()
    await db.commit()
    return {
        "planId": plan_id,
        "docId": doc.id,
        "reverted": 1,
        "needsReindex": bool(doc.excluded_ranges or (doc.raw_content or "") != previous_raw),
    }


async def organize_documents(
    db: AsyncSession,
    user_id: int,
    *,
    doc_ids: Optional[List[int]] = None,
    kb_id: Optional[int] = None,
) -> Dict[str, Any]:
    """整理单个/多个文档，返回可展示的 before/after diff 和 batchId。"""
    if not doc_ids and kb_id is None:
        raise ValueError("organize_documents 需要 doc_ids 或 kb_id")

    if kb_id is not None:
        from app.services.rag.rag_write_service import get_knowledge_base

        await get_knowledge_base(db, user_id, kb_id)
        stmt = select(RagDocument).where(
            RagDocument.user_id == user_id,
            RagDocument.kb_id == kb_id,
        )
    else:
        stmt = select(RagDocument).where(
            RagDocument.user_id == user_id,
            RagDocument.id.in_(doc_ids or []),
        )

    docs = (await db.execute(stmt)).scalars().all()
    batch_id = uuid4().hex
    changes: List[Dict[str, Any]] = []

    for doc in docs:
        before = _doc_snapshot(doc)
        result = analyze_material(
            doc.file_name or "",
            doc.raw_content or "",
            None,
            len(doc.image_map or {}),
        )
        doc.original_file_name = doc.original_file_name or result["original_file_name"]
        doc.file_name = result["display_name"]
        doc.subject = result["subject"]
        doc.material_type = result["material_type"]
        doc.facets = result["facets"]
        after = _doc_snapshot(doc)
        if before != after:
            db.add(
                MaterialOrganizeLog(
                    user_id=user_id,
                    batch_id=batch_id,
                    doc_id=doc.id,
                    before_json=before,
                    after_json=after,
                )
            )
            changes.append({"before": before, "after": after})

    await db.commit()
    return {"batchId": batch_id, "changes": changes, "count": len(changes)}


async def rollback_organize(db: AsyncSession, user_id: int, batch_id: str) -> Dict[str, Any]:
    """整批回退智能整理；只恢复日志里记录的字段。"""
    logs = (
        await db.execute(
            select(MaterialOrganizeLog).where(
                MaterialOrganizeLog.user_id == user_id,
                MaterialOrganizeLog.batch_id == batch_id,
                MaterialOrganizeLog.undone_at.is_(None),
            )
        )
    ).scalars().all()

    reverted = 0
    for log in logs:
        doc = (
            await db.execute(
                select(RagDocument).where(
                    RagDocument.id == log.doc_id,
                    RagDocument.user_id == user_id,
                )
            )
        ).scalars().first()
        if doc and log.before_json:
            b = log.before_json
            doc.file_name = b.get("fileName") or doc.file_name
            doc.original_file_name = b.get("originalFileName") or doc.original_file_name
            doc.subject = b.get("subject") or None
            doc.material_type = b.get("materialType") or None
            doc.facets = b.get("facets") or None
            doc.excluded_ranges = b.get("excludedRanges") or []
            reverted += 1
        log.undone_at = datetime.now()

    await db.commit()
    return {"batchId": batch_id, "reverted": reverted}
