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

import re
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import RagDocument, RagKnowledgeBase

#: 默认知识库在界面上显示的名字（用户不可改）
#: 与普通知识库并列展示，所以名字要像"一个库"，而不是"一个特殊区域"
WORKSPACE_NAME = "默认知识库"
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
            "fileType": d.file_type,
            "fileSize": d.file_size,
            "sizeText": _size_text(d.file_size or 0),
            "note": d.user_note or "",
            "chunkCount": d.chunk_count or 0,
            "status": d.status,
            "statusText": _status_text(d.status),
            "errorMsg": d.error_msg or "",
            "createTime": d.create_time.strftime("%Y-%m-%d %H:%M") if d.create_time else None,
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
        "createTime": d.create_time.strftime("%Y-%m-%d") if d.create_time else None,
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
                "name": kb.name,
                "description": kb.description or "",
                "isDefault": 1 if kb.is_workspace == 1 else 0,
                "disabled": 1 if kb.disabled == 1 else 0,
                "docCount": len(files),
                "chunkCount": sum(int(f.get("chunkCount") or 0) for f in files),
                "createTime": kb.create_time.strftime("%Y-%m-%d") if kb.create_time else None,
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
