# -*- coding: utf-8 -*-
"""后台管理：评论管理（/system/comment/*）

背景：前端「评论管理」页面（openstudy-vue3-ts/src/views/comment/comment/index.vue）
走的是 `/system/comment/*` 这组 RuoYi 风格接口，但 **后端从未实现**，
请求全部落到 catch_all 兜底：
  - GET  /system/comment/list        → 路径含 list，兜底返回 paginate(0, []) → 列表永远空
  - GET  /system/comment/{id}        → 兜底 success(None) → 查看对话框空白
  - PUT  /system/comment             → 兜底 success(None) → 弹「修改成功」但数据没变
  - DELETE /system/comment/{ids}     → 兜底 success(None) → 弹「删除成功」但没删

本文件按页面实际契约补齐这 4 个接口（行字段含 noteTitle/userName/replyUserName，
status 必须回字符串 "0"/"1"，因为页面用 `scope.row.status === '0'` 判断）。
评论管理属后台功能，非管理员一律 403。
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, paginate, error
from app.models.note import Note, NoteComment
from app.models.user import SysUser

router = APIRouter()


class CommentAdminUpdate(BaseModel):
    """后台修改评论请求（页面只用到 显示/隐藏，这里顺带支持改内容）

    Pydantic 默认忽略多余字段，页面提交的 noteTitle/userName/createTime 等会被忽略。
    """
    commentId: int
    status: Optional[str] = None
    content: Optional[str] = None


def _require_admin(current_user: dict):
    """评论管理是后台功能（对应页面 v-hasPermi 的 system:comment:*）"""
    if "admin" not in (current_user.get("roles") or []):
        return error("权限不足，仅管理员可管理评论", code=403)
    return None


def _format_admin_comment(c, note=None, user=None, reply_user=None) -> dict:
    """后台评论行：字段与页面 el-table-column 的 prop 一一对应"""
    return {
        "commentId": c.id,
        "id": c.id,
        "noteId": c.note_id,
        "noteTitle": note.title if note else "",
        # 页面用 scope.row.status === '0' 判断，必须是字符串
        "status": str(c.status if c.status is not None else 0),
        "userId": c.user_id,
        "userName": (user.nick_name or user.user_name) if user else "",
        "content": c.content,
        "parentId": c.parent_id,
        "replyToUserId": c.reply_to_user_id,
        "replyUserName": (reply_user.nick_name or reply_user.user_name) if reply_user else "",
        "createTime": c.create_time.isoformat() if c.create_time else None,
    }


async def _enrich_comments(db: AsyncSession, comments: list) -> list:
    """批量补笔记标题 / 评论人 / 被回复人（避免 N+1）"""
    if not comments:
        return []
    note_ids = {c.note_id for c in comments if c.note_id}
    user_ids = {c.user_id for c in comments if c.user_id}
    user_ids |= {c.reply_to_user_id for c in comments if c.reply_to_user_id}

    note_map = {}
    if note_ids:
        note_rows = await db.execute(select(Note).where(Note.note_id.in_(note_ids)))
        note_map = {n.note_id: n for n in note_rows.scalars().all()}

    user_map = {}
    if user_ids:
        user_rows = await db.execute(select(SysUser).where(SysUser.user_id.in_(user_ids)))
        user_map = {u.user_id: u for u in user_rows.scalars().all()}

    return [
        _format_admin_comment(c, note_map.get(c.note_id), user_map.get(c.user_id),
                              user_map.get(c.reply_to_user_id))
        for c in comments
    ]


@router.get("/system/comment/list")
async def list_comments_admin(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    noteId: Optional[int] = Query(None),
    userName: Optional[str] = Query(None),
    content: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    # 页面传的是 queryParams.params = {beginTime, endTime}，
    # axios 拦截器会序列化成 params[beginTime]=...&params[endTime]=...，故用别名接
    beginTime: Optional[str] = Query(None, alias="params[beginTime]"),
    endTime: Optional[str] = Query(None, alias="params[endTime]"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """评论列表（后台管理：支持笔记ID/用户名称/内容/状态/时间范围筛选）"""
    denied = _require_admin(current_user)
    if denied:
        return denied

    from app.api.v1.questions import _begin_of_date, _end_of_date

    query = select(NoteComment)

    if noteId is not None:
        query = query.where(NoteComment.note_id == noteId)
    if content:
        query = query.where(NoteComment.content.ilike(f"%{content}%"))
    if status not in (None, ""):
        try:
            query = query.where(NoteComment.status == int(status))
        except (TypeError, ValueError):
            return error("评论状态参数不合法", code=400)
    if userName:
        sub = select(SysUser.user_id).where(or_(
            SysUser.nick_name.ilike(f"%{userName}%"),
            SysUser.user_name.ilike(f"%{userName}%"),
        ))
        query = query.where(NoteComment.user_id.in_(sub))
    if beginTime:
        query = query.where(NoteComment.create_time >= _begin_of_date(beginTime))
    if endTime:
        query = query.where(NoteComment.create_time <= _end_of_date(endTime))

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(NoteComment.create_time.desc(), NoteComment.id.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)
    result = await db.execute(query)
    comments = list(result.scalars().all())

    rows = await _enrich_comments(db, comments)
    return paginate(total, rows)


@router.get("/system/comment/{comment_id}")
async def get_comment_admin(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """评论详情（后台「查看」对话框）"""
    denied = _require_admin(current_user)
    if denied:
        return denied

    comment = (await db.execute(
        select(NoteComment).where(NoteComment.id == comment_id)
    )).scalar_one_or_none()
    if not comment:
        return error("评论不存在")

    rows = await _enrich_comments(db, [comment])
    return success(rows[0])


@router.put("/system/comment")
async def update_comment_admin(
    payload: CommentAdminUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """修改评论（后台「显示/隐藏」；也支持改内容）"""
    denied = _require_admin(current_user)
    if denied:
        return denied

    comment = (await db.execute(
        select(NoteComment).where(NoteComment.id == payload.commentId)
    )).scalar_one_or_none()
    if not comment:
        return error("评论不存在")

    if payload.status is not None and payload.status != "":
        try:
            comment.status = int(payload.status)
        except (TypeError, ValueError):
            return error("评论状态参数不合法", code=400)
    if payload.content is not None:
        if not payload.content.strip():
            return error("评论内容不能为空", code=400)
        comment.content = payload.content

    return success()


@router.delete("/system/comment/{ids}")
async def delete_comments_admin(
    ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除评论（后台批量；删一级评论时连带删除其下回复，并同步笔记评论数）

    历史问题：/system/comment 未实现，删除只会命中 catch_all 返回「操作成功」，
    数据其实没删。这里同时做一致性处理：
      1. 一级评论的回复一并删除（否则回复会变成孤儿）
      2. 受影响笔记的 comment_count 同步扣减
    """
    denied = _require_admin(current_user)
    if denied:
        return denied

    id_list = []
    for x in str(ids).split(","):
        x = x.strip()
        if x.lstrip("-").isdigit():
            id_list.append(int(x))
    if not id_list:
        return error("评论ID不能为空", code=400)

    targets = list((await db.execute(
        select(NoteComment).where(NoteComment.id.in_(id_list))
    )).scalars().all())
    if not targets:
        return success()

    target_ids = [c.id for c in targets]
    children = list((await db.execute(
        select(NoteComment).where(NoteComment.parent_id.in_(target_ids))
    )).scalars().all())
    all_ids = target_ids + [c.id for c in children if c.id not in target_ids]

    # 统计每个笔记被删掉的评论条数（一级 + 回复），用于扣减 comment_count
    dec = {}
    for c in targets + children:
        dec[c.note_id] = dec.get(c.note_id, 0) + 1

    await db.execute(delete(NoteComment).where(NoteComment.id.in_(all_ids)))

    if dec:
        notes = list((await db.execute(
            select(Note).where(Note.note_id.in_(list(dec.keys())))
        )).scalars().all())
        for n in notes:
            n.comment_count = max(0, (n.comment_count or 0) - dec.get(n.note_id, 0))

    return success()
