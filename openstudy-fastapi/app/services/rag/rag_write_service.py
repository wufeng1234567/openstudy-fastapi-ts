"""
RAG 写服务（知识库 / 文档 / 分块）

与 `question_write_service.py` / `note_write_service.py` 同一套路：
领域逻辑放这里，工具层与 API 层只做参数校验 + 话术。

**权限**：本模块所有函数都要求调用方传入已校验归属的 `user_id`，
且每个操作都会再校验一次「这个 KB/文档是不是这个用户的」——
不信任任何来自请求体的 userId（这是 SpringBoot 版 `/rag/**` permit-all 的教训）。
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

from loguru import logger
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import (
    DOC_FAILED,
    DOC_PENDING,
    DOC_VECTORIZED,
    RagDocument,
    RagDocumentChunk,
    RagKnowledgeBase,
)
from app.services.rag.tokenizer import tokenize

KB_NAME_MAX = 255
DOC_NAME_MAX = 255
#: 单个知识库最多文档数（防止一次传太多把 embedding 额度打穿）
MAX_DOCS_PER_KB = 200

_NUL_RE = re.compile("\x00")


def sanitize_text(text: Optional[str]) -> str:
    """清掉 PostgreSQL 不接受、而 MySQL 会静默接受的字符。

    ⚠️ **PG 的 text/varchar 列不允许 NUL（`0x00`）**，写入直接抛
    `CharacterNotInRepertoireError: invalid byte sequence for encoding "UTF8": 0x00`；
    MySQL 则会把 NUL 原样存下来。所以这是「迁到 PG 之后才会暴露」的一类问题，
    二进制文件（或损坏的 docx）被当文本解析时最容易带上它。

    顺带丢掉无法编码成 UTF-8 的代理对残留 —— 同样是 MySQL 能存、PG 会拒的字符。
    """
    if not text:
        return text or ""
    text = _NUL_RE.sub("", text)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        logger.warning("[rag] 文本含非法 UTF-8 字符，已丢弃这些字符")
        text = text.encode("utf-8", "ignore").decode("utf-8")
    return text


class RagNotFound(Exception):
    """知识库 / 文档不存在，或不属于当前用户（刻意不区分，避免探测他人资源是否存在）"""


class RagConflict(Exception):
    """命名冲突等可预期的业务冲突"""


# ---------------------------------------------------------------- 知识库

async def list_knowledge_bases(
    db: AsyncSession, user_id: int, *, include_disabled: bool = True
) -> list[dict]:
    """当前用户的知识库清单。

    `include_disabled` 刻意做成**关键字参数**、默认 `True`（= 管理列表的口径）：
    被屏蔽的库**必须照样列出来**，否则用户自己的那个开关就再也关不掉了
    （列表里没有它 → 界面上什么都点不到）。

    ⚠️ 面向模型的路径必须显式传 `include_disabled=False` —— 目前只有两处：
    `ai/agent/runtime_context._kb_block`（L1 提示词里的知识库清单）与
    `ai/agent/tools/knowledge_search._list`（工具的 action=list）。这两处少一个，
    屏蔽就会有漏口。
    """
    stmt = select(RagKnowledgeBase).where(
        RagKnowledgeBase.user_id == user_id,
        RagKnowledgeBase.del_flag == "0",
    )
    if not include_disabled:
        stmt = stmt.where(RagKnowledgeBase.disabled == 0)
    rows = (
        await db.execute(
            stmt.order_by(RagKnowledgeBase.create_time.desc(), RagKnowledgeBase.id.desc())
        )
    ).scalars().all()
    return [_kb_brief(kb) for kb in rows]


async def get_knowledge_base(db: AsyncSession, user_id: int, kb_id: int) -> RagKnowledgeBase:
    """取知识库并校验归属。不属于该用户时抛 RagNotFound（不区分「不存在」以防探测）。"""
    kb = (
        await db.execute(
            select(RagKnowledgeBase).where(
                RagKnowledgeBase.id == kb_id,
                RagKnowledgeBase.del_flag == "0",
            )
        )
    ).scalar_one_or_none()
    if kb is None or kb.user_id != user_id:
        raise RagNotFound(f"知识库不存在或无权访问：{kb_id}")
    return kb


async def resolve_knowledge_bases(
    db: AsyncSession, user_id: int, kb_ids: Optional[Sequence[int]] = None
) -> list[RagKnowledgeBase]:
    """把可检索的知识库解析出来。

    `kb_ids` 为空 → 返回该用户**全部**知识库（比 legacy「必须绑定单个 kb，
    否则报未绑定」更可用）。传入的 id 里若有不属于该用户的，**直接抛错**而不是静默忽略
    —— 静默忽略会掩盖越权尝试。

    **屏蔽闸门就落在这里**（`/rag/search`、`/rag/ask`、
    `ai/agent/tools/knowledge_search._search` 全部经由此函数，所以只要这里挡住了，
    这条链路上没有任何一条能绕过）：被屏蔽的知识库**一律不出现在返回值里**。

    两条分支的写法**刻意不同**，别顺手改成一致的：
    · 默认分支（没点名）在 **SQL 里**过滤 `disabled = 0`；
    · 显式分支（点名了 id）**先按 id 取、再在内存里跳过屏蔽的** —— 因为那一支
      「取不到 / 不是你的」要**抛 RagNotFound**，若把 `disabled = 0` 也塞进 WHERE，
      一个被用户自己屏蔽的库会变成「知识库不存在或无权访问」→ `code=404`
      → 前端弹出**两条**没有任何信息量的错误提示（`errorCode['404']` 在前端字典里
      优先于后端文案，见前端 `src/utils/request.ts`）。屏蔽是用户的**主动动作**，
      呈现成报错是错的。所以显式分支里屏蔽的库**静默丢弃**：
      全都屏蔽 → 返回空列表 → 上层走既有的「没有可检索的知识库」兜底（`code=200`）。
    """
    if not kb_ids:
        rows = (
            await db.execute(
                select(RagKnowledgeBase).where(
                    RagKnowledgeBase.user_id == user_id,
                    RagKnowledgeBase.del_flag == "0",
                    RagKnowledgeBase.disabled == 0,
                )
            )
        ).scalars().all()
        return list(rows)

    # ⚠️ 这里**不能**把 `disabled == 0` 加进 WHERE（理由见 docstring）
    rows = (
        await db.execute(
            select(RagKnowledgeBase).where(
                RagKnowledgeBase.id.in_(list(kb_ids)),
                RagKnowledgeBase.del_flag == "0",
            )
        )
    ).scalars().all()
    found = {kb.id: kb for kb in rows}
    resolved: list[RagKnowledgeBase] = []
    for kid in kb_ids:
        kb = found.get(int(kid))
        if kb is None or kb.user_id != user_id:
            raise RagNotFound(f"知识库不存在或无权访问：{kid}")
        if kb.disabled:
            # 已屏蔽 → 静默丢弃（不抛错、也不告诉模型「它被屏蔽了」，见 docstring）
            continue
        resolved.append(kb)
    return resolved


async def create_knowledge_base(
    db: AsyncSession, user_id: int, name: str, description: Optional[str] = None
) -> RagKnowledgeBase:
    name = sanitize_text(name).strip()
    if not name:
        raise RagConflict("知识库名称不能为空")
    if len(name) > KB_NAME_MAX:
        raise RagConflict(f"知识库名称过长（最多 {KB_NAME_MAX} 字）")

    dup = (
        await db.execute(
            select(RagKnowledgeBase.id).where(
                RagKnowledgeBase.user_id == user_id,
                RagKnowledgeBase.name == name,
                RagKnowledgeBase.del_flag == "0",
            )
        )
    ).first()
    if dup:
        raise RagConflict(f"已存在同名知识库「{name}」")

    kb = RagKnowledgeBase(
        user_id=user_id, name=name, description=sanitize_text(description)
    )
    db.add(kb)
    await db.commit()
    # create_time 是 server_default，commit 后需要 refresh 才有值，
    # 否则序列化时会触发懒加载 —— 异步下直接 MissingGreenlet。
    await db.refresh(kb)
    return kb


async def update_knowledge_base(
    db: AsyncSession,
    user_id: int,
    kb_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    disabled: Optional[int] = None,
) -> RagKnowledgeBase:
    # ⚠️ 归属校验照旧走 get_knowledge_base（第 175 行那句）—— 新增的 disabled 字段
    #    绝不能绕过它，否则 PUT /rag/knowledgeBase/{id} 会变成「登进去就能屏蔽别人的库」。
    kb = await get_knowledge_base(db, user_id, kb_id)

    # 与 create_knowledge_base 同一口径：写库前一律过 sanitize_text（见其说明）
    if name is not None:
        name = sanitize_text(name).strip()
        if not name:
            raise RagConflict("知识库名称不能为空")
        kb.name = name
    if description is not None:
        kb.description = sanitize_text(description)
    if disabled is not None:
        # 归一化成 0/1：闸门那一侧判的是 `disabled == 0`（**非零即屏蔽**），
        # 而前端开关判的是 `disabled === 1`。库里若存进 2 这种值，两边就会分叉
        # —— 「界面显示已启用、模型却检索不到」，这种不一致比写反还难查。
        kb.disabled = 1 if int(disabled) else 0

    await db.commit()
    await db.refresh(kb)
    return kb


async def delete_knowledge_base(db: AsyncSession, user_id: int, kb_id: int) -> dict:
    """逻辑删知识库，并**物理清掉它的文档与分块**。

    为什么文档不分逻辑删：分块带着 1024 维向量，留着既占空间又可能被检索到
    （检索条件是 `kb.del_flag='0'`，但万一哪天有人直接按 chunk 查就会漏出来）。
    一并删干净更安全。
    """
    kb = await get_knowledge_base(db, user_id, kb_id)

    doc_ids = [
        r[0]
        for r in (
            await db.execute(select(RagDocument.id).where(RagDocument.kb_id == kb.id))
        ).all()
    ]
    chunks = 0
    if doc_ids:
        chunks = (
            await db.execute(
                select(func.count()).select_from(RagDocumentChunk).where(
                    RagDocumentChunk.doc_id.in_(doc_ids)
                )
            )
        ).scalar() or 0
        await db.execute(delete(RagDocumentChunk).where(RagDocumentChunk.doc_id.in_(doc_ids)))
        await db.execute(delete(RagDocument).where(RagDocument.id.in_(doc_ids)))

    kb.doc_count = 0
    kb.chunk_count = 0
    kb.del_flag = "2"  # 与笔记一致：逻辑删用 '2'
    await db.commit()
    logger.info(f"[rag] 删除知识库 id={kb.id} name={kb.name} 连带 {len(doc_ids)} 文档 / {chunks} 分块")
    return {"kbId": kb.id, "name": kb.name, "documents": len(doc_ids), "chunks": chunks}


# ---------------------------------------------------------------- 文档

async def list_documents(db: AsyncSession, user_id: int, kb_id: int) -> list[dict]:
    kb = await get_knowledge_base(db, user_id, kb_id)
    rows = (
        await db.execute(
            select(RagDocument)
            .where(RagDocument.kb_id == kb.id)
            .order_by(RagDocument.create_time.desc(), RagDocument.id.desc())
        )
    ).scalars().all()
    return [_doc_brief(d) for d in rows]


async def get_document(db: AsyncSession, user_id: int, doc_id: int) -> RagDocument:
    """取文档并校验归属 + **所属知识库未被逻辑删**。

    ⚠️ 第二个条件是必须的：`delete_knowledge_base` 虽然会连带物理删掉文档与分块，
    但那是**另一个事务里的尽力而为** —— 万一清理失败，只按 docId 取就会把
    「已删知识库」的正文/分块继续读出来。过滤口径与 `list_documents` 一致
    （经 `get_knowledge_base` 保证 `del_flag='0'` 且属于该用户）。
    """
    doc = (
        await db.execute(
            select(RagDocument)
            .join(RagKnowledgeBase, RagKnowledgeBase.id == RagDocument.kb_id)
            .where(
                RagDocument.id == doc_id,
                RagDocument.user_id == user_id,
                RagKnowledgeBase.user_id == user_id,
                RagKnowledgeBase.del_flag == "0",
            )
        )
    ).scalar_one_or_none()
    if doc is None:
        raise RagNotFound(f"文档不存在或无权访问：{doc_id}")
    return doc


async def delete_document(db: AsyncSession, user_id: int, doc_id: int) -> dict:
    doc = await get_document(db, user_id, doc_id)
    chunks = (
        await db.execute(
            select(func.count()).select_from(RagDocumentChunk).where(
                RagDocumentChunk.doc_id == doc.id
            )
        )
    ).scalar() or 0
    await db.execute(delete(RagDocumentChunk).where(RagDocumentChunk.doc_id == doc.id))
    await db.execute(delete(RagDocument).where(RagDocument.id == doc.id))
    await _refresh_kb_counts(db, doc.kb_id)
    await db.commit()
    return {"docId": doc.id, "fileName": doc.file_name, "chunks": chunks}


async def _refresh_kb_counts(db: AsyncSession, kb_id: int) -> None:
    """重算知识库的文档数 / 分块数。

    用 count 重算而不是 ±1 累加 —— 累加在异常/重试路径下会漂移，且这种漂移很难发现。
    """
    docs = (
        await db.execute(
            select(func.count()).select_from(RagDocument).where(RagDocument.kb_id == kb_id)
        )
    ).scalar() or 0
    chunks = (
        await db.execute(
            select(func.count()).select_from(RagDocumentChunk).where(
                RagDocumentChunk.kb_id == kb_id
            )
        )
    ).scalar() or 0
    await db.execute(
        update(RagKnowledgeBase)
        .where(RagKnowledgeBase.id == kb_id)
        .values(doc_count=docs, chunk_count=chunks)
    )


# ---------------------------------------------------------------- 分块

def build_chunk_rows(
    kb_id: int,
    doc_id: int,
    contents: Sequence[str],
    vectors: Optional[Sequence[list[float]]] = None,
) -> list[RagDocumentChunk]:
    """把分块文本（+ 可选向量）组装成 ORM 对象。

    `content_tokens` 必须在这里用 jieba 生成 —— PG 的 `search_vec` 是它的生成列，
    漏了这一步中文就检索不到（`search_vec` 会是空 tsvector）。
    """
    rows: list[RagDocumentChunk] = []
    for i, content in enumerate(contents):
        content = sanitize_text(content)
        rows.append(
            RagDocumentChunk(
                kb_id=kb_id,
                doc_id=doc_id,
                chunk_index=i,
                content=content,
                content_length=len(content),
                token_count=len(content),
                content_tokens=tokenize(content),
                embedding=list(vectors[i]) if vectors else None,
            )
        )
    return rows


async def create_document(
    db: AsyncSession,
    user_id: int,
    kb_id: int,
    *,
    file_name: str,
    raw_content: str,
    file_type: Optional[str] = None,
    file_size: Optional[int] = None,
    file_path: Optional[str] = None,
    status: int = DOC_PENDING,
) -> RagDocument:
    kb = await get_knowledge_base(db, user_id, kb_id)

    # NUL / 非法 UTF-8 必须在这里清掉，否则 PG 直接拒收（见 sanitize_text 的说明）
    raw_content = sanitize_text(raw_content)
    file_name = sanitize_text(file_name).strip() or "未命名文档"
    if len(file_name) > DOC_NAME_MAX:
        file_name = file_name[:DOC_NAME_MAX]

    existing = (
        await db.execute(
            select(func.count()).select_from(RagDocument).where(RagDocument.kb_id == kb.id)
        )
    ).scalar() or 0
    if existing >= MAX_DOCS_PER_KB:
        raise RagConflict(f"单个知识库最多 {MAX_DOCS_PER_KB} 篇文档")

    doc = RagDocument(
        kb_id=kb.id,
        user_id=user_id,
        file_name=file_name,
        file_type=file_type,
        file_size=file_size if file_size is not None else len(raw_content or ""),
        file_path=file_path,
        raw_content=raw_content,
        chunk_count=0,
        status=status,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def replace_chunks(
    db: AsyncSession,
    doc: RagDocument,
    contents: Sequence[str],
    vectors: Optional[Sequence[list[float]]] = None,
) -> int:
    """替换某文档的全部分块（先删后插，天然幂等，重向量化也走这里）。"""
    await db.execute(delete(RagDocumentChunk).where(RagDocumentChunk.doc_id == doc.id))
    rows = build_chunk_rows(doc.kb_id, doc.id, contents, vectors)
    db.add_all(rows)

    doc.chunk_count = len(rows)
    doc.status = DOC_VECTORIZED if vectors else DOC_PENDING
    if vectors:
        doc.error_msg = None
    await _refresh_kb_counts(db, doc.kb_id)
    await db.commit()
    return len(rows)


async def mark_document_failed(db: AsyncSession, doc: RagDocument, message: str) -> None:
    doc.status = DOC_FAILED
    # error_msg 是 varchar(500)，截断避免二次报错把真实原因盖掉
    doc.error_msg = (message or "")[:490]
    await db.commit()


async def list_chunks(db: AsyncSession, user_id: int, doc_id: int, limit: int = 200) -> list[dict]:
    doc = await get_document(db, user_id, doc_id)
    rows = (
        await db.execute(
            select(RagDocumentChunk)
            .where(RagDocumentChunk.doc_id == doc.id)
            .order_by(RagDocumentChunk.chunk_index)
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "chunkId": c.id,
            "chunkIndex": c.chunk_index,
            "content": c.content,
            "contentLength": c.content_length,
            "vectorized": c.embedding is not None,
        }
        for c in rows
    ]


# ---------------------------------------------------------------- 序列化

def kb_disabled_flag(kb: RagKnowledgeBase) -> int:
    """读侧唯一出口：把 `disabled` 归一成**整数 0/1**。

    ⚠️ 为什么必须归一、不能原样下发：前端的开关是**受控**的（显示值只来自服务端），
    而 `el-switch`（实测 element-plus 2.14.5）在 setup 体里有一段**裸 if** ——
    绑定值**既不是 activeValue 也不是 inactiveValue** 时（`undefined`/`null`、字符串
    `'1'`、甚至 `2`），它会**在挂载时** emit 一次 `update:modelValue(inactiveValue)`。
    抽屉若无条件 PUT，那就是「打开抽屉 = 替用户把每一行改成未屏蔽」的 N 次真实写库。

    所以这里保证三点：键**永远存在**、值**永远是 int 0/1**、绝不为 `None` / 字符串。
    非零一律归一成 1 —— 与闸门那一侧 `disabled == 0`（非零即屏蔽）**同向**，
    UI 显示与检索闸门因此不可能给出相反的结论。
    """
    return 1 if int(kb.disabled or 0) else 0


def _kb_brief(kb: RagKnowledgeBase) -> dict:
    return {
        "kbId": kb.id,
        "name": kb.name,
        "description": kb.description,
        "docCount": kb.doc_count,
        "chunkCount": kb.chunk_count,
        "disabled": kb_disabled_flag(kb),
        "embeddingModel": kb.embedding_model,
        "chunkSize": kb.chunk_size,
        "chunkOverlap": kb.chunk_overlap,
        "createTime": kb.create_time.isoformat(sep=" ") if kb.create_time else None,
    }


def _doc_brief(doc: RagDocument) -> dict:
    from app.models.rag import DOC_STATUS_TEXT

    return {
        "docId": doc.id,
        "kbId": doc.kb_id,
        "fileName": doc.file_name,
        "fileType": doc.file_type,
        "fileSize": doc.file_size,
        "chunkCount": doc.chunk_count,
        "status": doc.status,
        "statusText": DOC_STATUS_TEXT.get(doc.status, "未知"),
        "errorMsg": doc.error_msg,
        "createTime": doc.create_time.isoformat(sep=" ") if doc.create_time else None,
    }
