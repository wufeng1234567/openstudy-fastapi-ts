"""
RAG 写服务（知识库 / 文档 / 分块）

与 `question_write_service.py` / `note_write_service.py` 同一套路：
领域逻辑放这里，工具层与 API 层只做参数校验 + 话术。

**权限**：本模块所有函数都要求调用方传入已校验归属的 `user_id`，
且每个操作都会再校验一次「这个 KB/文档是不是这个用户的」——
不信任任何来自请求体的 userId（这是 SpringBoot 版 `/rag/**` permit-all 的教训）。
"""

from __future__ import annotations

import difflib
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence
from uuid import uuid4

from loguru import logger
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import (
    DOC_FAILED,
    DOC_PARSING,
    DOC_PENDING,
    DOC_VECTORIZED,
    MaterialOrganizeLog,
    MaterialOrganizePlan,
    RagDocument,
    RagDocumentChunk,
    RagKnowledgeBase,
)
from app.services.rag.tokenizer import tokenize

KB_NAME_MAX = 255
DOC_NAME_MAX = 255
#: 单个知识库最多文档数（防止一次传太多把 embedding 额度打穿）
MAX_DOCS_PER_KB = 200
#: 手动编辑版本快照复用 material_organize_log，批次前缀与整理计划区分。
VERSION_BATCH_PREFIX = "version:"
MAX_VERSIONS_PER_DOC = 20

_NUL_RE = re.compile("\x00")

#: 正文里的图片位置标记（与 `file_parser.IMAGE_MARKER_TMPL` 同形）。
#: RAG 端**只读**它（把图归属到分块），不生成 —— 生成在解析侧 `build_marked_document`。
IMAGE_MARKER_RE = re.compile(r"【图(\d+)】")


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
        raise RagNotFound(f"资料夹不存在或无权访问：{kb_id}")
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
            raise RagNotFound(f"资料夹不存在或无权访问：{kid}")
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
        raise RagConflict("资料夹名称不能为空")
    if len(name) > KB_NAME_MAX:
        raise RagConflict(f"资料夹名称过长（最多 {KB_NAME_MAX} 字）")

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
        raise RagConflict(f"已存在同名资料夹「{name}」")

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
            raise RagConflict("资料夹名称不能为空")
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

    docs = list(
        (await db.execute(select(RagDocument).where(RagDocument.kb_id == kb.id))).scalars().all()
    )
    doc_ids = [d.id for d in docs]
    physical_paths: list[str] = []
    for d in docs:
        if d.file_path:
            physical_paths.append(str(d.file_path))
        for value in (d.image_map or {}).values():
            if isinstance(value, str) and value.startswith("/profile/"):
                physical_paths.append(value)
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
    from app.utils.file_util import delete_file
    for item in physical_paths:
        relative = item[len("/profile/"):] if item.startswith("/profile/") else item
        try:
            delete_file(relative)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[rag] 删除知识库物理文件失败 {relative}: {e}")
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


def _version_snapshot(doc: RagDocument) -> dict:
    return {
        "fileName": doc.file_name or "",
        "originalFileName": doc.original_file_name or doc.file_name or "",
        "subject": doc.subject or "",
        "materialType": doc.material_type or "",
        "facets": doc.facets or {},
        "excludedRanges": doc.excluded_ranges or [],
        "rawContent": doc.raw_content or "",
        "imageMap": doc.image_map or {},
        "contentStructure": doc.content_structure or [],
        # 同名覆盖/恢复时文件元信息也要跟着回滚，否则会出现「正文是旧版、扩展名是新版」。
        "fileType": doc.file_type or "",
        "fileSize": int(doc.file_size or 0),
        "filePath": doc.file_path or "",
    }


def _version_summary(snapshot: dict) -> str:
    text = re.sub(r"【图\d+】", " ", str(snapshot.get("rawContent") or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:80]


def _version_time(value: Optional[datetime]) -> str:
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")


async def _add_version_log(
    db: AsyncSession, doc: RagDocument, snapshot: dict, reason: str
) -> MaterialOrganizeLog:
    log = MaterialOrganizeLog(
        user_id=doc.user_id,
        batch_id=f"{VERSION_BATCH_PREFIX}{uuid4().hex}",
        doc_id=doc.id,
        before_json=snapshot,
        after_json={"reason": reason, "docId": doc.id},
    )
    db.add(log)
    await db.flush()
    # 每个文档只保留最近 N 个版本，避免历史正文无限膨胀。
    stale = (
        await db.execute(
            select(MaterialOrganizeLog.id)
            .where(
                MaterialOrganizeLog.user_id == doc.user_id,
                MaterialOrganizeLog.doc_id == doc.id,
                MaterialOrganizeLog.batch_id.like(f"{VERSION_BATCH_PREFIX}%"),
            )
            .order_by(MaterialOrganizeLog.create_time.desc(), MaterialOrganizeLog.id.desc())
            .offset(MAX_VERSIONS_PER_DOC)
        )
    ).scalars().all()
    if stale:
        await db.execute(delete(MaterialOrganizeLog).where(MaterialOrganizeLog.id.in_(stale)))
    return log


async def _create_version_log(
    db: AsyncSession, doc: RagDocument, reason: str = "保存前自动快照"
) -> MaterialOrganizeLog:
    return await _add_version_log(db, doc, _version_snapshot(doc), reason)


async def list_document_versions(
    db: AsyncSession, user_id: int, doc_id: int, limit: int = 30
) -> list[dict]:
    doc = await get_document(db, user_id, doc_id)
    rows = (
        await db.execute(
            select(MaterialOrganizeLog)
            .where(
                MaterialOrganizeLog.user_id == user_id,
                MaterialOrganizeLog.doc_id == doc.id,
                MaterialOrganizeLog.batch_id.like(f"{VERSION_BATCH_PREFIX}%"),
            )
            .order_by(MaterialOrganizeLog.create_time.desc(), MaterialOrganizeLog.id.desc())
            .limit(max(1, min(limit, 100)))
        )
    ).scalars().all()
    out = []
    for log in rows:
        snapshot = log.before_json or {}
        out.append(
            {
                "versionId": log.id,
                "docId": doc.id,
                "fileName": snapshot.get("fileName") or doc.file_name,
                "reason": (log.after_json or {}).get("reason") or "保存前自动快照",
                "summary": _version_summary(snapshot),
                "contentLength": len(snapshot.get("rawContent") or ""),
                "createTime": _version_time(log.create_time),
            }
        )
    return out


async def get_document_version(
    db: AsyncSession, user_id: int, doc_id: int, version_id: int
) -> dict:
    doc = await get_document(db, user_id, doc_id)
    log = (
        await db.execute(
            select(MaterialOrganizeLog).where(
                MaterialOrganizeLog.id == version_id,
                MaterialOrganizeLog.user_id == user_id,
                MaterialOrganizeLog.doc_id == doc.id,
                MaterialOrganizeLog.batch_id.like(f"{VERSION_BATCH_PREFIX}%"),
            )
        )
    ).scalar_one_or_none()
    if not log:
        raise RagNotFound("历史版本不存在或无权访问")
    snapshot = log.before_json or {}
    return {
        "versionId": log.id,
        "docId": doc.id,
        "fileName": snapshot.get("fileName") or doc.file_name,
        "reason": (log.after_json or {}).get("reason") or "保存前自动快照",
        "createTime": _version_time(log.create_time),
        "content": snapshot.get("rawContent") or "",
        "imageMap": snapshot.get("imageMap") or {},
        "contentStructure": snapshot.get("contentStructure") or [],
        "excludedRanges": snapshot.get("excludedRanges") or [],
    }


def _diff_rows(old: str, new: str, max_rows: int = 600) -> tuple[list[dict], dict]:
    """按行生成左右对照 diff；遇到超长文本只截展示行，不改统计。"""
    old_lines = str(old or "").splitlines()
    new_lines = str(new or "").splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    rows: list[dict] = []
    added = 0
    removed = 0
    left_no = 1
    right_no = 1
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                rows.append(
                    {
                        "type": "same",
                        "leftNo": left_no,
                        "rightNo": right_no,
                        "left": old_lines[i1 + offset][:240],
                        "right": new_lines[j1 + offset][:240],
                    }
                )
                left_no += 1
                right_no += 1
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                removed += 1
                rows.append({"type": "remove", "leftNo": left_no, "rightNo": None, "left": line[:240], "right": ""})
                left_no += 1
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                added += 1
                rows.append({"type": "add", "leftNo": None, "rightNo": right_no, "left": "", "right": line[:240]})
                right_no += 1
        else:  # replace
            old_chunk = old_lines[i1:i2]
            new_chunk = new_lines[j1:j2]
            length = max(len(old_chunk), len(new_chunk))
            for idx in range(length):
                left = old_chunk[idx] if idx < len(old_chunk) else ""
                right = new_chunk[idx] if idx < len(new_chunk) else ""
                if idx < len(old_chunk):
                    removed += 1
                    left_no += 1
                if idx < len(new_chunk):
                    added += 1
                    right_no += 1
                rows.append(
                    {
                        "type": "change" if left and right else ("remove" if left else "add"),
                        "leftNo": left_no - 1 if left else None,
                        "rightNo": right_no - 1 if right else None,
                        "left": left[:240],
                        "right": right[:240],
                    }
                )
    stats = {
        "addedLines": added,
        "removedLines": removed,
        "oldLines": len(old_lines),
        "newLines": len(new_lines),
        "oldChars": len(old),
        "newChars": len(new),
        "charDelta": len(new) - len(old),
    }
    return rows[:max_rows], stats


def _health_snapshot(snapshot: dict, doc_id: int) -> dict:
    """对任意历史快照跑一次与「资料体检」同源的规则计算，保证前后口径一致。"""
    from types import SimpleNamespace

    from app.services.document_health_service import build_document_health

    fake = SimpleNamespace(
        id=int(doc_id),
        file_name=str(snapshot.get("fileName") or ""),
        raw_content=str(snapshot.get("rawContent") or ""),
        image_map=snapshot.get("imageMap") or {},
        content_structure=snapshot.get("contentStructure") or [],
        material_type=str(snapshot.get("materialType") or ""),
    )
    report = build_document_health(fake)
    return {
        "score": int(report.get("score") or 0),
        "grade": report.get("grade") or {},
        "issueCount": len(report.get("issues") or []),
        "stats": report.get("stats") or {},
        "metrics": [
            {"key": m.get("key"), "label": m.get("label"), "score": m.get("score")}
            for m in (report.get("metrics") or [])
        ],
    }


async def diff_document_versions(
    db: AsyncSession,
    user_id: int,
    doc_id: int,
    from_id: int,
    to_id: int = 0,
) -> dict:
    """历史版本 ↔ 当前/另一历史版本的可解释 diff。

    `to_id=0` 表示当前正文；这样用户不需要先为当前内容创建一个版本。
    """
    doc = await get_document(db, user_id, doc_id)

    async def load_snapshot(version_id: int) -> tuple[dict, dict]:
        if int(version_id) == 0:
            return _version_snapshot(doc), {
                "versionId": 0,
                "fileName": doc.file_name or "",
                "reason": "当前正文",
                "createTime": _version_time(doc.update_time or doc.create_time),
            }
        log = (
            await db.execute(
                select(MaterialOrganizeLog).where(
                    MaterialOrganizeLog.id == int(version_id),
                    MaterialOrganizeLog.user_id == user_id,
                    MaterialOrganizeLog.doc_id == doc.id,
                    MaterialOrganizeLog.batch_id.like(f"{VERSION_BATCH_PREFIX}%"),
                )
            )
        ).scalar_one_or_none()
        if not log:
            raise RagNotFound("历史版本不存在或无权访问")
        snap = log.before_json or {}
        return snap, {
            "versionId": int(log.id),
            "fileName": snap.get("fileName") or doc.file_name or "",
            "reason": (log.after_json or {}).get("reason") or "保存前自动快照",
            "createTime": _version_time(log.create_time),
        }

    old_snapshot, old_meta = await load_snapshot(from_id)
    new_snapshot, new_meta = await load_snapshot(to_id)
    old_text = str(old_snapshot.get("rawContent") or "")
    new_text = str(new_snapshot.get("rawContent") or "")
    rows, stats = _diff_rows(old_text, new_text)
    before_health = _health_snapshot(old_snapshot, int(doc.id))
    after_health = _health_snapshot(new_snapshot, int(doc.id))
    return {
        "docId": int(doc.id),
        "fileName": doc.file_name or "",
        "from": old_meta,
        "to": new_meta,
        "identical": old_text == new_text,
        "rows": rows,
        "stats": stats,
        "health": {
            "before": before_health,
            "after": after_health,
            "scoreDelta": after_health["score"] - before_health["score"],
            "issueDelta": after_health["issueCount"] - before_health["issueCount"],
        },
    }


async def restore_document_version(
    db: AsyncSession, user_id: int, doc_id: int, version_id: int
) -> dict:
    """恢复某个历史版本；恢复前先把当前内容也存成一个版本，操作可再次撤销。"""
    doc = await get_document(db, user_id, doc_id)
    if doc.status == DOC_PARSING:
        raise ValueError("这份资料正在解析/向量化中，请等当前处理完成后再恢复版本")
    log = (
        await db.execute(
            select(MaterialOrganizeLog).where(
                MaterialOrganizeLog.id == version_id,
                MaterialOrganizeLog.user_id == user_id,
                MaterialOrganizeLog.doc_id == doc.id,
                MaterialOrganizeLog.batch_id.like(f"{VERSION_BATCH_PREFIX}%"),
            )
        )
    ).scalar_one_or_none()
    if not log:
        raise RagNotFound("历史版本不存在或无权访问")
    snapshot = log.before_json or {}
    if not (snapshot.get("rawContent") or "").strip():
        raise ValueError("这个历史版本没有可恢复的正文")

    await _create_version_log(db, doc, "恢复历史版本前的自动快照")
    doc.raw_content = snapshot.get("rawContent") or ""
    doc.file_name = snapshot.get("fileName") or doc.file_name
    doc.original_file_name = snapshot.get("originalFileName") or doc.original_file_name
    doc.subject = snapshot.get("subject") or None
    doc.material_type = snapshot.get("materialType") or None
    doc.facets = snapshot.get("facets") or None
    doc.excluded_ranges = snapshot.get("excludedRanges") or []
    doc.image_map = snapshot.get("imageMap") or None
    doc.content_structure = snapshot.get("contentStructure") or []
    doc.file_type = snapshot.get("fileType") or doc.file_type
    doc.file_size = int(snapshot.get("fileSize") or doc.file_size or 0)
    doc.file_path = snapshot.get("filePath") or doc.file_path
    doc.status = DOC_PENDING
    doc.error_msg = None
    doc.version = int(doc.version or 1) + 1
    doc.index_version = int(doc.index_version or 1) + 1
    doc.update_time = datetime.utcnow()
    await db.commit()
    return {
        "docId": doc.id,
        "versionId": version_id,
        "fileName": doc.file_name,
        "status": doc.status,
        "needsReindex": True,
    }


async def set_document_disabled(
    db: AsyncSession, user_id: int, doc_id: int, disabled: bool
) -> dict:
    """单文档检索开关；只改 disabled，不动分块/向量。"""
    doc = await get_document(db, user_id, doc_id)
    doc.disabled = 1 if disabled else 0
    await db.commit()
    return {
        "docId": doc.id,
        "fileName": doc.file_name,
        "disabled": doc.disabled,
    }


async def update_document_content(
    db: AsyncSession,
    user_id: int,
    doc_id: int,
    content: str,
    file_name: Optional[str] = None,
) -> dict:
    """保存二次编辑后的正文，标记待重新解析。"""
    doc = await get_document(db, user_id, doc_id)
    if doc.status in (DOC_PENDING, DOC_PARSING):
        raise ValueError("这份资料正在解析/向量化中，请等当前处理完成后再修改")
    cleaned = sanitize_text(content or "").strip()
    if not cleaned:
        raise ValueError("正文不能为空")
    before_snapshot = _version_snapshot(doc)
    if file_name and str(file_name).strip():
        doc.file_name = str(file_name).strip()[:255]
    doc.raw_content = cleaned
    # 旧剔除范围基于旧正文偏移，编辑后必须清空，避免错删新内容；
    # 块结构同样要重建，否则智能整理会拿旧偏移误判代码/公式。
    doc.excluded_ranges = []
    try:
        from app.services.file_parser import parse_file

        parsed = parse_file("document.md", cleaned.encode("utf-8"))
        doc.content_structure = parsed.get("contentStructure") or []
    except Exception:  # noqa: BLE001 - 结构重建失败不应阻断保存
        doc.content_structure = []
    # 编辑器保存时可能删掉了某些图片标记；只保留正文里仍存在的图片资产。
    if doc.image_map:
        present = {int(match.group(1)) for match in re.finditer(r"【图(\d+)】", cleaned)}
        doc.image_map = {
            str(key): value
            for key, value in (doc.image_map or {}).items()
            if str(key).isdigit() and int(key) in present
        } or None
    version_log = None
    if before_snapshot != _version_snapshot(doc):
        version_log = await _add_version_log(db, doc, before_snapshot, "编辑保存前自动快照")
    doc.status = DOC_PENDING
    doc.error_msg = None
    doc.version = int(doc.version or 1) + 1
    doc.index_version = int(doc.index_version or 1) + 1
    await db.commit()
    return {
        "docId": doc.id,
        "fileName": doc.file_name,
        "status": doc.status,
        "statusText": "待解析",
        "contentLength": len(cleaned),
        "version": int(doc.version or 1),
        # 供 Agent 回执/前端做“恢复这次修改前的版本”入口。
        "versionId": version_log.id if version_log else None,
    }


async def delete_document(db: AsyncSession, user_id: int, doc_id: int) -> dict:
    doc = await get_document(db, user_id, doc_id)
    # 收集物理文件：原始文件 + 解析出的插图。先记路径，删库成功后统一清盘。
    physical_paths: list[str] = []
    if doc.file_path:
        physical_paths.append(str(doc.file_path))
    for value in (doc.image_map or {}).values():
        if isinstance(value, str) and value.startswith("/profile/"):
            physical_paths.append(value)
    chunks = (
        await db.execute(
            select(func.count()).select_from(RagDocumentChunk).where(
                RagDocumentChunk.doc_id == doc.id
            )
        )
    ).scalar() or 0
    await db.execute(delete(RagDocumentChunk).where(RagDocumentChunk.doc_id == doc.id))
    # 资料删除后，依附于它的整理计划和旧版整理日志一并清理；否则历史列表会出现
    # 指向不存在资料的“幽灵记录”，用户也无法再回退或查看。
    await db.execute(
        delete(MaterialOrganizePlan).where(MaterialOrganizePlan.doc_id == doc.id)
    )
    await db.execute(
        delete(MaterialOrganizeLog).where(MaterialOrganizeLog.doc_id == doc.id)
    )
    # 题目原文锚点依附于资料：资料物理删除后锚点必须一起清，避免留下孤儿行。
    from app.models.question import QuestionSource

    await db.execute(
        delete(QuestionSource).where(
            QuestionSource.doc_id == doc.id,
            QuestionSource.user_id == user_id,
        )
    )
    await db.execute(delete(RagDocument).where(RagDocument.id == doc.id))
    await _refresh_kb_counts(db, doc.kb_id)
    await db.commit()
    # 数据库删除成功后再清盘，避免回滚后文件却先没了（无法恢复）
    from app.utils.file_util import delete_file
    for item in physical_paths:
        relative = item[len("/profile/"):] if item.startswith("/profile/") else item
        try:
            delete_file(relative)
        except Exception as e:  # noqa: BLE001 - 文件清理失败不阻断删除语义
            logger.warning(f"[rag] 删除资料物理文件失败 {relative}: {e}")
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


# ---------------------------------------------------------------- 图片落盘

def persist_document_images(image_data_urls: Sequence[str]) -> dict:
    """把文档解析出的图片（data URL 列表）落盘，返回 `{"0": "/profile/upload/...", ...}`。

    为什么落盘而不是把 base64 存库：见 `models/rag.py` 的 `image_map` 注释
    （data URL 上百 KB，落盘后才能被前端 `<img>` 直接显示，也便于回给模型前转回）。

    `image_data_urls` 的顺序必须与正文里的 `【图N】` 一一对应（N 从 0 起）。
    单张落盘失败不影响其它图 —— 记录日志后跳过，不阻断整篇文档入库。

    ⚠️ 只接受 `data:` 前缀的 data URL（解析器 `_payload_to_data_url` 的产物）；
      http(s) 外链不下载（避免 SSRF / 断网卡死），直接原样保留 URL 而不落盘。
    """
    from app.utils.file_util import save_bytes

    mapping: dict[str, str] = {}
    for idx, data_url in enumerate(image_data_urls or []):
        value = (data_url or "").strip()
        if not value:
            continue
        try:
            if value.startswith("http://") or value.startswith("https://"):
                # 外链图：不下载，原样记为可用 URL（前端/模型都能直接取）
                mapping[str(idx)] = value
                continue
            blob, mime = _data_url_to_bytes(value)  # 见下方辅助函数
            ext = _mime_to_ext(mime)
            saved = save_bytes(blob, f"rag_image_{idx}.{ext}", sub_dir="upload")
            mapping[str(idx)] = saved["fileUrl"]
        except Exception as e:  # noqa: BLE001 - 单张失败不该拖垮整篇
            logger.warning(f"[rag] 第 {idx} 张图落盘失败，已跳过：{e}")
    return mapping


def _data_url_to_bytes(data_url: str) -> tuple[bytes, str]:
    """`data:image/png;base64,xxxx` → (bytes, mime)。非法输入抛 ValueError。"""
    import base64

    head, _, payload = data_url.partition(",")
    if not payload:
        raise ValueError("不是合法的 data URL")
    mime = "image/png"
    if head.startswith("data:"):
        meta = head[len("data:"):]
        mime = meta.split(";", 1)[0] or "image/png"
    padded = payload + "=" * (-len(payload) % 4)
    return base64.b64decode(padded), mime


def _mime_to_ext(mime: str) -> str:
    m = (mime or "").lower()
    if "jpeg" in m or "jpg" in m:
        return "jpg"
    if "gif" in m:
        return "gif"
    if "webp" in m:
        return "webp"
    if "bmp" in m:
        return "bmp"
    return "png"


# ---------------------------------------------------------------- 分块

def _image_indexes_in_text(text: str) -> list[int]:
    """扫出正文里的 `【图N】` 标记，返回出现过的 N（顺序即出现顺序，可重复）。"""
    return [int(m) for m in IMAGE_MARKER_RE.findall(text or "")]


def build_chunk_rows(
    kb_id: int,
    doc_id: int,
    contents: Sequence[str],
    vectors: Optional[Sequence[list[float]]] = None,
    image_map: Optional[dict] = None,
    index_version: int = 1,
) -> list[RagDocumentChunk]:
    """把分块文本（+ 可选向量）组装成 ORM 对象。

    `content_tokens` 必须在这里用 jieba 生成 —— PG 的 `search_vec` 是它的生成列，
    漏了这一步中文就检索不到（`search_vec` 会是空 tsvector）。

    `image_map`（`{"0": "/profile/...", ...}`）非空时：扫本块正文里的 `【图N】`，
    把命中的图片 URL 记进 `meta_data["images"]` —— 检索命中这一块时就能把图一起回给模型
    （见 `hybrid_search.ChunkHit`）。块内没有标记就不写，保持 `meta_data` 为空（与历史一致）。
    """
    rows: list[RagDocumentChunk] = []
    img_map = image_map or {}
    for i, content in enumerate(contents):
        content = sanitize_text(content)
        meta = None
        if img_map:
            hit_urls: list[str] = []
            for n in _image_indexes_in_text(content):
                url = img_map.get(str(n))
                if url and url not in hit_urls:
                    hit_urls.append(url)
            if hit_urls:
                meta = {"images": hit_urls}
        rows.append(
            RagDocumentChunk(
                kb_id=kb_id,
                doc_id=doc_id,
                chunk_index=i,
                index_version=index_version,
                content=content,
                content_length=len(content),
                token_count=len(content),
                content_tokens=tokenize(content),
                embedding=list(vectors[i]) if vectors else None,
                meta_data=meta,
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
    image_map: Optional[dict] = None,
    content_structure: Optional[list] = None,
    original_file_name: Optional[str] = None,
    subject: Optional[str] = None,
    material_type: Optional[str] = None,
    facets: Optional[dict] = None,
    status: int = DOC_PENDING,
    on_duplicate: str = "newVersion",
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
        raise RagConflict(f"单个资料夹最多 {MAX_DOCS_PER_KB} 篇文档")

    # 同名资料策略（2026-11-04 从「一律拒绝」改为「默认生成新版本」）：
    #   · newVersion（默认）→ 同名但内容不同：旧正文快照进历史版本，当前文档升到 vN+1；
    #   · reject            → 保留旧的「拒绝重复」行为，供明确不想覆盖的调用方使用。
    # 同名且正文完全一致 → 直接复用原文档（防用户误点两次上传凭空多一版）。
    dup = (
        await db.execute(
            select(RagDocument).where(
                RagDocument.kb_id == kb.id,
                (RagDocument.file_name == file_name)
                | (RagDocument.original_file_name == (original_file_name or file_name)),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if dup is not None:
        strategy = (on_duplicate or "newVersion").strip().lower()
        if strategy == "reject":
            raise RagConflict(f"同名资料已存在：{file_name}，请先删除或改名后再上传")
        if (dup.raw_content or "") == raw_content:
            # 完全相同的正文不制造空版本；调用方从 _upload_unchanged 标记得到提示。
            dup._upload_unchanged = True  # type: ignore[attr-defined]
            return dup
        await _create_version_log(db, dup, "上传新版本前自动快照")
        dup.file_name = file_name
        dup.original_file_name = original_file_name or file_name
        dup.subject = subject
        dup.material_type = material_type
        dup.facets = facets
        dup.file_type = file_type
        dup.file_size = file_size if file_size is not None else len(raw_content or "")
        dup.file_path = file_path
        dup.raw_content = raw_content
        dup.image_map = image_map or None
        dup.content_structure = content_structure or None
        dup.chunk_count = 0
        dup.status = status
        dup.error_msg = None
        dup.version = int(dup.version or 1) + 1
        # 旧 chunks 保留但在检索时按 index_version 排除，避免重向量化期间命中旧正文。
        dup.index_version = int(dup.index_version or 1) + 1
        dup.update_time = datetime.utcnow()
        await _refresh_kb_counts(db, kb.id)
        await db.commit()
        await db.refresh(dup)
        dup._was_versioned = True  # type: ignore[attr-defined]
        logger.info(
            f"[rag] 同名资料生成新版本 doc={dup.id} version={dup.version} name={file_name}"
        )
        return dup

    doc = RagDocument(
        kb_id=kb.id,
        user_id=user_id,
        file_name=file_name,
        original_file_name=original_file_name or file_name,
        subject=subject,
        material_type=material_type,
        facets=facets,
        file_type=file_type,
        file_size=file_size if file_size is not None else len(raw_content or ""),
        file_path=file_path,
        raw_content=raw_content,
        image_map=image_map or None,
        content_structure=content_structure or None,
        chunk_count=0,
        status=status,
    )
    db.add(doc)
    await db.flush()
    # 上传后立即刷新计数，列表/侧栏不用等向量化完成才看到「N 份资料」
    await _refresh_kb_counts(db, kb.id)
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
    rows = build_chunk_rows(
        doc.kb_id,
        doc.id,
        contents,
        vectors,
        image_map=doc.image_map,
        index_version=int(doc.index_version or 1),
    )
    db.add_all(rows)

    doc.chunk_count = len(rows)
    doc.status = DOC_VECTORIZED if vectors else DOC_PENDING
    doc.update_time = datetime.utcnow()
    if vectors:
        doc.error_msg = None
    await _refresh_kb_counts(db, doc.kb_id)
    await db.commit()
    return len(rows)


async def mark_document_failed(db: AsyncSession, doc: RagDocument, message: str) -> None:
    doc.status = DOC_FAILED
    # error_msg 是 varchar(500)，截断避免二次报错把真实原因盖掉
    doc.error_msg = (message or "")[:490]
    doc.update_time = datetime.utcnow()
    await db.commit()


async def list_chunks(db: AsyncSession, user_id: int, doc_id: int, limit: int = 200) -> list[dict]:
    doc = await get_document(db, user_id, doc_id)
    rows = (
        await db.execute(
            select(RagDocumentChunk)
            .where(
                RagDocumentChunk.doc_id == doc.id,
                RagDocumentChunk.index_version == doc.index_version,
            )
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
            # 该分块夹带的图片（`/profile/...` 相对路径）。前端据此把正文里的
            # `【图N】` 标记渲染成缩略图（原来只回 content，图信息被丢掉，
            # 于是预览里只剩一个光秃秃的「【图0】」）。
            "images": _chunk_images(c),
        }
        for c in rows
    ]


def _chunk_images(chunk: RagDocumentChunk) -> list:
    """从分块 `meta_data` 取图片 URL 列表（容错：任何异常 = 无图）。"""
    try:
        meta = chunk.meta_data
        if not isinstance(meta, dict):
            return []
        imgs = meta.get("images")
        return [str(u) for u in imgs if u] if isinstance(imgs, list) else []
    except Exception:  # noqa: BLE001
        return []


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
        # 默认资料夹也允许用户改名，所以始终返回数据库里的 name。
        "name": kb.name,
        "description": kb.description,
        "docCount": kb.doc_count,
        "chunkCount": kb.chunk_count,
        "disabled": kb_disabled_flag(kb),
        # 默认库标记：前端据此在列表里显示「默认」徽标，并禁止改名/删除
        "isDefault": 1 if getattr(kb, "is_workspace", 0) == 1 else 0,
        "sourceType": getattr(kb, "source_type", "self") or "self",
        "sourceKbId": getattr(kb, "source_kb_id", None),
        "shareId": getattr(kb, "share_id", None),
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
        "version": int(getattr(doc, "version", 1) or 1),
        "chunkCount": doc.chunk_count,
        "indexVersion": doc.index_version,
        "status": doc.status,
        "statusText": DOC_STATUS_TEXT.get(doc.status, "未知"),
        "disabled": 1 if getattr(doc, "disabled", 0) else 0,
        "sourceType": getattr(doc, "source_type", "self") or "self",
        "sourceDocId": getattr(doc, "source_doc_id", None),
        "shareId": getattr(doc, "share_id", None),
        "errorMsg": doc.error_msg,
        "createTime": doc.create_time.isoformat(sep=" ") if doc.create_time else None,
    }
