"""知识库分享 API。

完全参考题库分享的链路：
  知识库主 A 生成分享链接 / 分享码
    -> 用户 B 打开链接或输入分享码
    -> B 领取：把整个知识库深拷贝到 B 名下（含文档）
    -> 写领取记录 + 给 A 发通知

为什么知识库领取是「深拷贝」而不是像题库那样只发只读收藏：
知识库由多个文档组成，后续还可能继续上传、整理、重建索引；跨用户的
只读文档权限会渗透到上传 / 解析 / 删除 / 检索等整条链路，容易留下越权口子。
领取时复制成 B 自己的知识库，B 可以直接编辑、检索、继续添加资料，边界最清楚。
"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error, success
from app.core.security import get_current_user
from app.database import get_db
from app.models.bank_share import KbShare, KbShareReceive
from app.models.rag import RagDocument, RagKnowledgeBase
from app.models.user import SysUser
from app.services import kb_copy_service
from app.services.notification_service import create_notification
from app.services.rag import workspace_service
from app.services.rag.document_pipeline import process_document

router = APIRouter()

_CODE_ALPHABET = string.ascii_uppercase + string.digits


def _now() -> datetime:
    return datetime.now()


def _gen_token() -> str:
    return secrets.token_urlsafe(24)


def _gen_code(length: int = 6) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


async def _get_body(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


async def _owner_name(db: AsyncSession, user_id: int) -> str:
    if not user_id:
        return "未知用户"
    name = await db.scalar(select(SysUser.nick_name).where(SysUser.user_id == user_id))
    return name or f"用户{user_id}"


def _effective(share: KbShare) -> bool:
    if not share or share.status != "0":
        return False
    if share.expire_time and share.expire_time < _now():
        return False
    return True


def _format(share: KbShare, kb: Optional[RagKnowledgeBase] = None, owner_name: str = "", doc=None) -> dict:
    row = {
        "shareId": share.id,
        "kbId": share.kb_id,
        "docId": share.doc_id,
        "targetType": "document" if share.doc_id else "knowledge_base",
        "ownerId": share.owner_id,
        "shareToken": share.share_token,
        "shareCode": share.share_code,
        "permission": share.permission or "copy",
        "message": share.message,
        "expireTime": share.expire_time.isoformat() if share.expire_time else None,
        "receiveCount": share.receive_count or 0,
        "status": share.status,
        "effective": _effective(share),
        "createTime": share.create_time.isoformat() if share.create_time else None,
    }
    if kb is not None:
        row.update(
            {
                "kbName": kb.name,
                "description": kb.description or "",
                "docCount": kb.doc_count or 0,
                "chunkCount": kb.chunk_count or 0,
                "isDefault": 1 if kb.is_workspace == 1 else 0,
            }
        )
    if doc is not None:
        row["docName"] = doc.file_name
        row["docCount"] = 1
    if owner_name:
        row["ownerName"] = owner_name
    return row


async def _find_share(db: AsyncSession, token: Optional[str], code: Optional[str]) -> Optional[KbShare]:
    if token:
        share = (
            await db.execute(select(KbShare).where(KbShare.share_token == token))
        ).scalar_one_or_none()
        if share:
            return share
    if code:
        return (
            await db.execute(
                select(KbShare)
                .where(KbShare.share_code == str(code).strip().upper())
                .order_by(KbShare.create_time.desc())
            )
        ).scalars().first()
    return None


@router.post("/kbShare/kbShare/create")
async def create_kb_share(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """生成知识库分享（仅知识库主）。body: {kbId, docId?, expireDays?, message?}"""
    body = await _get_body(request)
    kb_id = body.get("kbId") or body.get("kb_id")
    doc_id = body.get("docId") or body.get("doc_id")
    user_id = int(current_user.get("user_id") or 0)
    doc = None
    if doc_id:
        doc = (
            await db.execute(
                select(RagDocument).where(
                    RagDocument.id == int(doc_id),
                    RagDocument.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if not doc:
            return error("文档不存在或无权分享", code=404)
        kb_id = doc.kb_id

    if not kb_id:
        return error("kbId 不能为空")

    kb = (
        await db.execute(
            select(RagKnowledgeBase).where(
                RagKnowledgeBase.id == int(kb_id),
                RagKnowledgeBase.del_flag == "0",
            )
        )
    ).scalar_one_or_none()
    if not kb:
        return error("知识库不存在")
    if int(kb.user_id) != user_id:
        return error("只有知识库主才能分享", code=403)
    if not doc_id and not kb.doc_count:
        return error("空知识库无法分享，请先添加资料")

    expire_days = body.get("expireDays")
    expire_time = None
    if expire_days not in (None, "", 0, "0"):
        try:
            expire_time = _now() + timedelta(days=int(expire_days))
        except (TypeError, ValueError):
            return error("有效期格式不正确")

    code = _gen_code()
    for _ in range(10):
        if not await db.scalar(select(func.count()).where(KbShare.share_code == code)):
            break
        code = _gen_code()

    share = KbShare(
        kb_id=int(kb_id),
        doc_id=int(doc_id) if doc_id else None,
        owner_id=user_id,
        share_token=_gen_token(),
        share_code=code,
        permission="copy",
        message=(body.get("message") or "").strip()[:200] or None,
        expire_time=expire_time,
        status="0",
    )
    db.add(share)
    await db.flush()
    await db.refresh(share)
    return success(_format(share, kb, await _owner_name(db, user_id), doc))


@router.get("/kbShare/kbShare/my")
async def my_kb_shares(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = int(current_user.get("user_id") or 0)
    shares = (
        await db.execute(
            select(KbShare).where(KbShare.owner_id == user_id).order_by(KbShare.create_time.desc())
        )
    ).scalars().all()
    if not shares:
        return success([])
    kb_ids = list({int(s.kb_id) for s in shares})
    kbs = (
        await db.execute(select(RagKnowledgeBase).where(RagKnowledgeBase.id.in_(kb_ids)))
    ).scalars().all()
    kb_map = {int(k.id): k for k in kbs}
    doc_ids = [int(s.doc_id) for s in shares if s.doc_id]
    docs = (
        await db.execute(select(RagDocument).where(RagDocument.id.in_(doc_ids)))
    ).scalars().all() if doc_ids else []
    doc_map = {int(d.id): d for d in docs}
    return success(
        [
            _format(
                s,
                kb_map.get(int(s.kb_id)),
                doc=doc_map.get(int(s.doc_id)) if s.doc_id else None,
            )
            for s in shares
        ]
    )


@router.post("/kbShare/kbShare/revoke/{share_id}")
async def revoke_kb_share(
    share_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = int(current_user.get("user_id") or 0)
    share = (await db.execute(select(KbShare).where(KbShare.id == share_id))).scalar_one_or_none()
    if not share:
        return error("分享不存在")
    if int(share.owner_id) != user_id:
        return error("无权撤销该分享", code=403)
    share.status = "1"
    share.update_time = _now()

    receives = (
        await db.execute(select(KbShareReceive).where(KbShareReceive.share_id == share_id))
    ).scalars().all()
    kb_name = await db.scalar(
        select(RagKnowledgeBase.name).where(RagKnowledgeBase.id == share.kb_id)
    ) or "知识库"
    doc_name = (
        await db.scalar(select(RagDocument.file_name).where(RagDocument.id == share.doc_id))
        if share.doc_id
        else None
    )
    shared_name = f"文档《{doc_name}》" if doc_name else f"知识库《{kb_name}》"
    for rec in receives:
        if rec.status == "0":
            rec.status = "1"
            rec.update_time = _now()
            await create_notification(
                db,
                user_id=int(rec.receiver_id),
                notify_type="share_invalid",
                title="你收到的分享已撤销",
                content=f"{shared_name}的分享已被撤销；你之前保存的副本仍然保留，可以继续使用。",
                link="/front/workspace",
            )
    await db.flush()
    return success()


async def _share_info(
    db: AsyncSession,
    current_user: dict,
    token: Optional[str] = None,
    code: Optional[str] = None,
):
    share = await _find_share(db, token, code)
    if not share:
        return error("分享不存在或已被删除", code=404)
    if share.status != "0":
        return error("该分享已被撤销", code=410)
    if share.expire_time and share.expire_time < _now():
        return error("该分享已过期", code=410)

    kb = (
        await db.execute(
            select(RagKnowledgeBase).where(
                RagKnowledgeBase.id == share.kb_id,
                RagKnowledgeBase.del_flag == "0",
            )
        )
    ).scalar_one_or_none()
    if not kb:
        return error("原知识库已被删除", code=404)

    doc = None
    if share.doc_id:
        doc = (
            await db.execute(
                select(RagDocument).where(
                    RagDocument.id == share.doc_id,
                    RagDocument.kb_id == share.kb_id,
                )
            )
        ).scalar_one_or_none()
        if not doc:
            return error("原文档已被删除", code=404)

    user_id = int(current_user.get("user_id") or 0)
    received = (
        await db.execute(
            select(KbShareReceive).where(
                KbShareReceive.share_id == share.id,
                KbShareReceive.receiver_id == user_id,
            )
        )
    ).scalar_one_or_none()

    data = _format(share, kb, await _owner_name(db, int(share.owner_id)), doc)
    data["received"] = received is not None
    data["newKbId"] = int(received.new_kb_id) if received and received.new_kb_id else None
    data["newDocId"] = int(received.new_doc_id) if received and received.new_doc_id else None
    data["isOwner"] = user_id == int(share.owner_id)
    return success(data)


@router.get("/kbShare/kbShare/info/{token}")
async def info_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await _share_info(db, current_user, token=token)


@router.get("/kbShare/kbShare/infoByCode/{code}")
async def info_by_code(
    code: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await _share_info(db, current_user, code=code)


@router.post("/kbShare/kbShare/receive")
async def receive_kb_share(
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """领取分享：深拷贝知识库 + 文档，返回领取者自己的新知识库。"""
    body = await _get_body(request)
    share = await _find_share(db, body.get("token"), body.get("code"))
    if not share:
        return error("分享不存在或已被删除", code=404)
    if share.status != "0":
        return error("该分享已被撤销", code=410)
    if share.expire_time and share.expire_time < _now():
        return error("该分享已过期", code=410)

    kb = (
        await db.execute(
            select(RagKnowledgeBase).where(
                RagKnowledgeBase.id == share.kb_id,
                RagKnowledgeBase.del_flag == "0",
            )
        )
    ).scalar_one_or_none()
    if not kb:
        return error("原知识库已被删除", code=404)

    user_id = int(current_user.get("user_id") or 0)
    if int(share.owner_id) == user_id:
        return error("这是你自己分享的资料，无需领取")

    source_doc = None
    if share.doc_id:
        source_doc = (
            await db.execute(
                select(RagDocument).where(
                    RagDocument.id == share.doc_id,
                    RagDocument.kb_id == share.kb_id,
                )
            )
        ).scalar_one_or_none()
        if not source_doc:
            return error("原文档已被删除", code=404)

    existed = (
        await db.execute(
            select(KbShareReceive).where(
                KbShareReceive.share_id == share.id,
                KbShareReceive.receiver_id == user_id,
            )
        )
    ).scalar_one_or_none()
    already_target = (existed.new_doc_id if share.doc_id else existed.new_kb_id) if existed else None
    if existed and already_target:
        return success(
            {
                "kbId": int(existed.new_kb_id) if existed.new_kb_id else None,
                "docId": int(existed.new_doc_id) if existed.new_doc_id else None,
                "kbName": kb.name,
                "docName": source_doc.file_name if source_doc else None,
                "alreadyReceived": True,
                "resultStatus": "exists",
            }
        )

    if source_doc:
        target_kb = await workspace_service.get_or_create_workspace(db, user_id)
        copied_doc = await kb_copy_service.copy_document_to_kb(
            db, source_doc, target_kb, user_id
        )
        background.add_task(process_document, copied_doc.id)
        new_kb = target_kb
        new_doc_id = int(copied_doc.id)
        pending_ids = []
    else:
        new_kb, pending_ids = await kb_copy_service.copy_knowledge_base(
            db, kb, user_id, new_name=f"{kb.name}（来自分享）"
        )
        for doc_id in pending_ids:
            background.add_task(process_document, doc_id)
        new_doc_id = None

    if existed:
        existed.status = "0"
        existed.new_kb_id = int(new_kb.id)
        existed.new_doc_id = new_doc_id
        existed.update_time = _now()
    else:
        db.add(
            KbShareReceive(
                share_id=share.id,
                kb_id=share.kb_id,
                owner_id=int(share.owner_id),
                receiver_id=user_id,
                new_kb_id=int(new_kb.id),
                new_doc_id=new_doc_id,
                source="share",
                status="0",
            )
        )
        share.receive_count = (share.receive_count or 0) + 1
        receiver_name = await _owner_name(db, user_id)
        shared_name = f"文档《{source_doc.file_name}》" if source_doc else f"知识库《{kb.name}》"
        await create_notification(
            db,
            user_id=int(share.owner_id),
            notify_type="share_receive",
            title="有人领取了你的分享",
            content=f"用户「{receiver_name}」领取了你分享的{shared_name}，系统已为对方生成副本。",
            link="/front/workspace",
        )

    await db.flush()
    return success(
        {
            "kbId": int(new_kb.id),
            "docId": new_doc_id,
            "kbName": new_kb.name,
            "docName": source_doc.file_name if source_doc else None,
            "docCount": int(new_kb.doc_count or 0) if not source_doc else 1,
            "alreadyReceived": False,
            "resultStatus": "created",
        }
    )
