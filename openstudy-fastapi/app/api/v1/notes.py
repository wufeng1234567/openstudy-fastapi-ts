"""
笔记 API - 完整实现
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, func, update, delete, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from loguru import logger
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, paginate, error
from app.models.note import Note, NoteCategory, NoteComment
from app.utils.excel_util import export_to_excel
from datetime import datetime, timedelta, time

router = APIRouter()


def _int_flag(value) -> int:
    """把 tinyint / 字符串形式的 0/1 归一成 int，前端用 `isPublic === 1` 判断"""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def format_note(note, linked_banks=None, author_name=None, author_avatar=None, is_favorited=False, hot_score=None):
    """格式化笔记数据

    linked_banks: 关联题库列表，形如 [{"questionBankId": 1, "bankName": "..."}]
    author_name: 作者昵称
    author_avatar: 作者头像
    is_favorited: 当前用户是否已收藏
    hot_score: 热榜综合热度分（仅排行榜场景传入）
    """
    return {
        "noteId": note.note_id,
        # 前端 editor.vue 发布后取的是 data.id，这里同步返回一份别名
        "id": note.note_id,
        "userId": note.user_id,
        "authorName": author_name or "",
        "avatar": author_avatar or "",
        "isFavorited": is_favorited,
        "categoryId": note.category_id,
        "title": note.title,
        # ⚠️ content 与 markdownContent **互相兜底**（读侧，覆盖历史数据）：前端所有笔记展示
        #    （详情页/列表/编辑器）只读 `markdownContent`，而 Agent 建的笔记可能只写了 `content`
        #    → 前端读到空 md 就一片空白（用户 2026-10-11 报）。故任一为空时用另一个补上。
        "content": note.content or note.markdown_content,
        "markdownContent": note.markdown_content or note.content,
        "tags": note.tags,
        "publicSectionId": note.public_section_id,
        "coverImage": note.cover_image,
        "isPublic": _int_flag(note.is_public),
        "viewCount": note.view_count,
        "likeCount": note.like_count,
        "commentCount": note.comment_count,
        "status": note.status,
        "createTime": note.create_time.isoformat() if note.create_time else None,
        "updateTime": note.update_time.isoformat() if note.update_time else None,
        "linkedBanks": linked_banks or [],
        # 热榜综合热度（非排行榜场景为 None，前端回退用 viewCount）
        "hotScore": hot_score,
    }


def format_category(cat):
    """格式化分类数据"""
    return {
        "id": cat.id,
        "userId": cat.user_id,
        "name": cat.name,
        "orderNum": cat.order_num,
        "createTime": cat.create_time.isoformat() if cat.create_time else None,
    }


def format_comment(comment, user=None, reply_to_user=None):
    """格式化评论数据"""
    return {
        "id": comment.id,
        "commentId": comment.id,
        "noteId": comment.note_id,
        "userId": comment.user_id,
        "userName": user.nick_name if user else (user.user_name if user else ""),
        "name": user.user_name if user else "",
        "avatar": user.avatar if user else "",
        "content": comment.content,
        "parentId": comment.parent_id,
        "replyToUserId": comment.reply_to_user_id,
        "replyToUserName": reply_to_user.nick_name if reply_to_user else "",
        "replyCount": 0,  # 默认值，会在 list_comments 和 get_comment_thread 中更新
        "status": comment.status,
        "createTime": comment.create_time.isoformat() if comment.create_time else None,
        "children": [],
    }


async def _fetch_linked_banks_map(db: AsyncSession, note_ids: list) -> dict:
    """批量查询笔记关联的题库，返回 {note_id: [{questionBankId, bankName}]}"""
    if not note_ids:
        return {}
    from app.models.note_question_bank import NoteQuestionBank
    from app.models.question import QuestionBank

    # 一次查询所有关联
    link_query = select(
        NoteQuestionBank.note_id,
        NoteQuestionBank.question_bank_id,
    ).where(NoteQuestionBank.note_id.in_(note_ids))
    link_result = await db.execute(link_query)
    links = [(row[0], row[1]) for row in link_result.all()]

    if not links:
        return {nid: [] for nid in note_ids}

    # 一次查询题库名称
    bank_ids = list({bid for _, bid in links})
    bank_query = select(QuestionBank.id, QuestionBank.bank_name).where(QuestionBank.id.in_(bank_ids))
    bank_result = await db.execute(bank_query)
    bank_name_map = {row[0]: row[1] for row in bank_result.all()}

    # 按 note_id 聚合
    result: dict = {nid: [] for nid in note_ids}
    for note_id, bank_id in links:
        result.setdefault(note_id, []).append({
            "questionBankId": bank_id,
            "bankName": bank_name_map.get(bank_id),
        })
    return result


async def _fetch_linked_banks(db: AsyncSession, note_id: int) -> list:
    """查询单条笔记的关联题库，返回 [{questionBankId, bankName}]"""
    return (await _fetch_linked_banks_map(db, [note_id])).get(note_id, [])


# ---------------------------------------------------------------- 归属校验
# 笔记/分类/评论都属于「个人数据」，只能由归属者本人读写；
# 公开笔记（is_public=1）额外允许他人只读。
# 这些接口此前只按 id 定位，任何登录用户都能凭 id 读取、篡改甚至删除他人数据（水平越权）。

def _is_admin(current_user: dict) -> bool:
    return "admin" in (current_user.get("roles") or [])


def _resolve_user_scope(current_user: dict, requested_user_id):
    """个人数据只允许查自己；管理员可查任意用户。返回 (user_id, err)"""
    current_id = current_user.get("user_id")
    if requested_user_id is None or int(requested_user_id) == int(current_id or 0):
        return current_id, None
    if _is_admin(current_user):
        return requested_user_id, None
    return None, error("无权查看他人数据", code=403)


async def _get_note_checked(db: AsyncSession, note_id, current_user: dict, allow_public: bool = False):
    """取笔记并做归属校验。返回 (note, err)，二者必有一为 None"""
    note = (await db.execute(
        select(Note).where(Note.note_id == note_id, Note.del_flag == "0")
    )).scalar_one_or_none()
    if not note:
        return None, error("笔记不存在")
    if int(note.user_id or 0) == int(current_user.get("user_id") or 0):
        return note, None
    if allow_public and _int_flag(note.is_public) == 1:
        return note, None
    return None, error("无权访问该笔记", code=403)


async def _deny_foreign_note_ids(db: AsyncSession, id_list, user_id, label: str = "笔记"):
    """批量操作前预检：只要涉及他人笔记就整体拒绝"""
    if not id_list:
        return None
    foreign = await db.scalar(
        select(func.count()).select_from(Note).where(
            Note.note_id.in_(id_list),
            Note.user_id != user_id,
        )
    )
    if foreign:
        return error("无权操作他人的%s" % label, code=403)
    return None


async def _deny_foreign_category_ids(db: AsyncSession, id_list, user_id, label: str = "分类"):
    """分类批量操作前预检"""
    if not id_list:
        return None
    foreign = await db.scalar(
        select(func.count()).select_from(NoteCategory).where(
            NoteCategory.id.in_(id_list),
            NoteCategory.user_id != user_id,
        )
    )
    if foreign:
        return error("无权操作他人的%s" % label, code=403)
    return None


# ========== 笔记 API ==========

@router.get("/notes/note/list")
async def list_notes(
    title: Optional[str] = Query(None),
    userId: Optional[int] = Query(None),
    categoryId: Optional[int] = Query(None),
    isPublic: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询笔记列表（仅本人；管理员可指定 userId）"""
    user_id, err = _resolve_user_scope(current_user, userId)
    if err:
        return err
    query = select(Note).where(Note.user_id == user_id, Note.del_flag == "0")

    if title:
        query = query.where(Note.title.ilike(f"%{title}%"))
    if categoryId:
        query = query.where(Note.category_id == categoryId)
    if isPublic:
        query = query.where(Note.is_public == _int_flag(isPublic))
    if status:
        query = query.where(Note.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(Note.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    notes = list(result.scalars().all())

    # 批量查询关联题库(避免 N+1)
    banks_map = await _fetch_linked_banks_map(db, [n.note_id for n in notes])

    # 获取当前用户信息作为作者
    from app.models.user import SysUser
    user_query = select(SysUser).where(SysUser.user_id == user_id)
    user_result = await db.execute(user_query)
    current_user_obj = user_result.scalar_one_or_none()

    return paginate(total, [
        format_note(
            n,
            banks_map.get(n.note_id, []),
            author_name=current_user_obj.nick_name if current_user_obj else None,
            author_avatar=current_user_obj.avatar if current_user_obj else None,
        )
        for n in notes
    ])


@router.get("/notes/note/public/list")
async def list_public_notes(
    title: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    userId: Optional[int] = Query(None),
    publicSectionId: Optional[int] = Query(None),
    publicSectionIds: Optional[str] = Query(None, description="多选分区，逗号分隔，如 1,2"),
    tag: Optional[str] = Query(None),
    tags: Optional[str] = Query(None, description="多选标签，逗号分隔，如 Java,Python"),
    timeRanges: Optional[str] = Query(None, description="多选时间区间，逗号分隔，如 today,7d,30d"),
    sortBy: Optional[str] = Query(None),
    sortOrder: Optional[str] = Query("desc"),
    startTime: Optional[str] = Query(None),
    endTime: Optional[str] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询公开笔记列表

    支持多选复合筛选（组内 OR、组间 AND）：
    - 关键词：标题 / 正文 / Markdown / 标签
    - 分区：publicSectionIds=1,2
    - 标签：tags=Java,Python
    - 时间：timeRanges=today,7d,30d（并集）+ 自定义 startTime/endTime
    - 排序：create_time / click_count / content_length
    """
    query = select(Note).where(Note.is_public == 1, Note.del_flag == "0")

    if title:
        query = query.where(Note.title.ilike(f"%{title}%"))
    if keyword:
        like = f"%{keyword}%"
        # 作者维度：昵称或用户名命中的作者，其公开笔记一并返回（如搜「若依」匹配昵称叫若依的作者）
        from app.models.user import SysUser
        query = query.where(or_(
            Note.title.ilike(like),
            Note.content.ilike(like),
            Note.markdown_content.ilike(like),
            Note.tags.ilike(like),
            Note.user_id.in_(
                select(SysUser.user_id).where(
                    or_(SysUser.nick_name.ilike(like), SysUser.user_name.ilike(like))
                )
            ),
        ))
    if userId:
        query = query.where(Note.user_id == userId)

    # 分区（多选，组内 OR；兼容旧的单选参数）
    section_ids = []
    if publicSectionIds:
        for raw in publicSectionIds.split(","):
            raw = raw.strip()
            if raw.lstrip("-").isdigit():
                section_ids.append(int(raw))
    if not section_ids and publicSectionId is not None:
        section_ids = [publicSectionId]
    if section_ids:
        query = query.where(Note.public_section_id.in_(section_ids))

    # 标签（多选，组内 OR；兼容旧的单选参数）
    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    if not tag_list and tag:
        tag_list = [tag]
    if tag_list:
        query = query.where(or_(*[Note.tags.ilike(f"%{t}%") for t in tag_list]))

    # 时间（多选，并集；可与自定义区间叠加）
    def _parse_dt(value: Optional[str]):
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    now = datetime.now()
    ranges = []
    range_keys = {r.strip() for r in (timeRanges or "").split(",") if r.strip()}
    if "today" in range_keys:
        ranges.append((now.replace(hour=0, minute=0, second=0, microsecond=0), now))
    if "7d" in range_keys:
        ranges.append((now - timedelta(days=6), now))
    if "30d" in range_keys:
        ranges.append((now - timedelta(days=29), now))
    if startTime or endTime:
        ranges.append((_parse_dt(startTime) or datetime(1970, 1, 1), _parse_dt(endTime) or now))
    if ranges:
        query = query.where(or_(*[
            and_(Note.create_time >= r_start, Note.create_time <= r_end)
            for r_start, r_end in ranges
        ]))

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # 排序：create_time（默认）/ click_count（浏览量）/ content_length（内容长度）
    # ⚠️ content_length 必须同时统计 content 与 markdown_content：
    #    前台编辑器只写 markdown_content，content 为 NULL，只按 content 排序时
    #    这些真正的长文会被判为最短（LENGTH(NULL) 为 NULL），「内容最长」完全失真；
    #    用 CHAR_LENGTH（字符数）而非 LENGTH（字节数），中英文权重才一致
    content_length_expr = (
        func.char_length(func.coalesce(Note.content, ""))
        + func.char_length(func.coalesce(Note.markdown_content, ""))
    )
    order_column = {
        "click_count": Note.view_count,
        "view_count": Note.view_count,
        "content_length": content_length_expr,
        "create_time": Note.create_time,
    }.get(sortBy or "create_time", Note.create_time)
    if (sortOrder or "desc").lower() == "asc":
        query = query.order_by(order_column.asc())
    else:
        query = query.order_by(order_column.desc())

    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    notes = list(result.scalars().all())

    # 批量查询关联题库(避免 N+1)
    banks_map = await _fetch_linked_banks_map(db, [n.note_id for n in notes])

    # 批量查询作者信息(避免 N+1)
    from app.models.user import SysUser
    author_ids = list(set(n.user_id for n in notes))
    author_map = {}
    if author_ids:
        author_query = select(SysUser).where(SysUser.user_id.in_(author_ids))
        author_result = await db.execute(author_query)
        for user in author_result.scalars().all():
            author_map[user.user_id] = user

    # 批量查询当前用户的收藏状态(避免 N+1)
    from app.models.note import UserNoteFavorite
    current_user_id = current_user.get("user_id")
    favorited_note_ids = set()
    if current_user_id:
        note_ids = [n.note_id for n in notes]
        fav_query = select(UserNoteFavorite.note_id).where(
            UserNoteFavorite.user_id == current_user_id,
            UserNoteFavorite.note_id.in_(note_ids)
        )
        fav_result = await db.execute(fav_query)
        favorited_note_ids = {row[0] for row in fav_result.fetchall()}

    return paginate(total, [
        format_note(
            n,
            banks_map.get(n.note_id, []),
            author_name=author_map[n.user_id].nick_name if n.user_id in author_map else None,
            author_avatar=author_map[n.user_id].avatar if n.user_id in author_map else None,
            is_favorited=n.note_id in favorited_note_ids,
        )
        for n in notes
    ])


@router.get("/notes/note/public/tags")
async def public_note_tags(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """公开笔记的热门标签（带出现次数），用于「学习分享」页的标签筛选

    注意：该路由必须注册在 /notes/note/public/{note_id} 之前，否则会被后者吞掉。
    """
    result = await db.execute(
        select(Note.tags).where(Note.is_public == 1, Note.del_flag == "0")
    )
    counter: dict = {}
    for (tags,) in result.all():
        for raw in str(tags or "").split(","):
            t = raw.strip()
            if t:
                counter[t] = counter.get(t, 0) + 1
    top = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return success([{"tag": t, "count": c} for t, c in top])


@router.get("/notes/note/public/ranking")
async def note_ranking(
    type: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """获取笔记排行榜

    - type=today：今日榜，统计「当天 0 点以来发布」的公开笔记
    - type=week ：周榜，统计「近 7 天发布」的公开笔记
    - 其他/空值 ：总榜，不做时间窗口限制（兼容旧调用）

    数据库只记录累计浏览量、没有按天浏览流水，因此榜单口径为
    「时间窗口内发布的笔记，按综合热度排序」。
    综合热度 = 浏览量 + 点赞数 * 3 + 评论数 * 5（互动行为权重更高）。
    """
    # 综合热度表达式（浏览 1 分、点赞 3 分、评论 5 分）
    hot_score_expr = (
        Note.view_count + Note.like_count * 3 + Note.comment_count * 5
    ).label("hot_score")

    stmt = select(Note, hot_score_expr).where(
        Note.is_public == 1,
        Note.del_flag == "0",
    )

    # 按榜单类型施加发布时间窗口
    now = datetime.now()
    if type == "today":
        today_start = datetime.combine(now.date(), time.min)
        stmt = stmt.where(Note.create_time >= today_start)
    elif type == "week":
        week_start = now - timedelta(days=7)
        stmt = stmt.where(Note.create_time >= week_start)
    elif type == "month":
        month_start = now - timedelta(days=30)
        stmt = stmt.where(Note.create_time >= month_start)
    elif type == "year":
        year_start = now - timedelta(days=365)
        stmt = stmt.where(Note.create_time >= year_start)

    # 热度优先，同热度时新发布的在前
    stmt = stmt.order_by(
        hot_score_expr.desc(), Note.create_time.desc()
    ).limit(limit)

    result = await db.execute(stmt)
    rows = result.all()
    notes = [row[0] for row in rows]
    score_map = {row[0].note_id: int(row[1] or 0) for row in rows}

    # 批量查询作者信息
    from app.models.user import SysUser
    author_ids = list(set(n.user_id for n in notes))
    author_map = {}
    if author_ids:
        author_query = select(SysUser).where(SysUser.user_id.in_(author_ids))
        author_result = await db.execute(author_query)
        for user in author_result.scalars().all():
            author_map[user.user_id] = user

    return success([
        format_note(
            n,
            author_name=author_map[n.user_id].nick_name if n.user_id in author_map else None,
            author_avatar=author_map[n.user_id].avatar if n.user_id in author_map else None,
            hot_score=score_map.get(n.note_id, n.view_count or 0),
        )
        for n in notes
    ])


@router.get("/notes/note/public/{note_id}")
async def get_public_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取笔记详情

    权限：
    - 本人：自己的笔记（公开 / 私密）都能看
    - 他人：只能看已公开的笔记

    注意：前端详情页统一走这个接口，因此不能再硬性要求 is_public=1，
    否则作者本人打开自己的私密笔记也会提示「笔记不存在」。
    """
    note, err = await _get_note_checked(db, note_id, current_user, allow_public=True)
    if err:
        return err

    # 增加浏览次数
    note.view_count += 1

    linked_banks = await _fetch_linked_banks(db, note.note_id)

    # 检查当前用户是否已收藏
    is_favorited = False
    current_user_id = current_user.get("user_id") if current_user else None
    if current_user_id:
        from app.models.note import UserNoteFavorite
        fav_query = select(UserNoteFavorite).where(
            UserNoteFavorite.user_id == current_user_id,
            UserNoteFavorite.note_id == note_id
        )
        fav_result = await db.execute(fav_query)
        is_favorited = fav_result.scalar_one_or_none() is not None

    return success(format_note(note, linked_banks, is_favorited=is_favorited))


@router.post("/notes/note/public/click/{note_id}")
async def record_click(
    note_id: int,
    db: AsyncSession = Depends(get_db),
):
    """记录笔记点击"""
    query = select(Note).where(Note.note_id == note_id, Note.del_flag == "0")
    result = await db.execute(query)
    note = result.scalar_one_or_none()

    if note:
        note.view_count += 1

    return success()


@router.get("/notes/note/{note_id}")
async def get_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取笔记详情（本人可见全部，他人只能看已公开笔记）"""
    note, err = await _get_note_checked(db, note_id, current_user, allow_public=True)
    if err:
        return err

    linked_banks = await _fetch_linked_banks(db, note.note_id)
    return success(format_note(note, linked_banks))


@router.post("/notes/note")
async def create_note(
    request: Request,
    title: Optional[str] = None,
    content: Optional[str] = None,
    categoryId: Optional[int] = None,
    category_id: Optional[int] = None,
    coverImage: Optional[str] = None,
    cover_image: Optional[str] = None,
    isPublic: Optional[int] = 0,
    is_public: Optional[int] = 0,
    status: Optional[str] = "draft",
    markdownContent: Optional[str] = None,
    markdown_content: Optional[str] = None,
    tags: Optional[str] = None,
    publicSectionId: Optional[int] = None,
    public_section_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建笔记

    支持查询参数和 JSON body 两种传参方式。
    JSON body 字段：title, content, markdownContent, tags, publicSectionId,
                    categoryId, coverImage, isPublic, status
    """
    # 兼容 JSON body 传参
    try:
        body = await request.json()
    except Exception:
        body = {}

    # 优先使用 JSON body 字段，回退到查询参数
    title = body.get("title") or title
    content = body.get("content") or content
    markdown_content = body.get("markdownContent") or body.get("markdown_content") or markdownContent or markdown_content
    tags = body.get("tags") or tags
    public_section_id = body.get("publicSectionId") or body.get("public_section_id") or publicSectionId or public_section_id
    category_id = body.get("categoryId") or body.get("category_id") or categoryId or category_id
    cover_image = body.get("coverImage") or body.get("cover_image") or coverImage or cover_image
    # isPublic 前端传的是数字 1/0，0 是合法值不能用 `or` 兜底
    raw_public = body.get("isPublic", body.get("is_public", isPublic))
    is_public = _int_flag(raw_public)
    status = body.get("status") or status

    if not title:
        return error("标题不能为空", code=400)

    # note.category_id 在库中是 NOT NULL：缺分类时提前给出业务提示，
    # 否则 INSERT 会抛 IntegrityError 变成 500 服务器内部错误
    if not category_id:
        return error("请先选择笔记分类", code=400)

    # 分类必须存在且属于当前用户，避免把笔记挂到他人分类下
    cat = (await db.execute(
        select(NoteCategory).where(
            NoteCategory.id == category_id,
            NoteCategory.user_id == current_user.get("user_id"),
        )
    )).scalar_one_or_none()
    if not cat:
        return error("笔记分类不存在", code=400)

    user_id = current_user.get("user_id")

    note = Note(
        user_id=user_id,
        title=title,
        content=content,
        markdown_content=markdown_content,
        tags=tags,
        public_section_id=public_section_id,
        category_id=category_id,
        cover_image=cover_image,
        is_public=is_public,
        status=status,
    )
    db.add(note)
    await db.flush()
    # create_time/update_time 由库端默认值生成，flush 后会标记为过期；
    # 必须在协程里显式 refresh，否则同步访问属性会触发懒加载 -> MissingGreenlet
    await db.refresh(note)

    return success(format_note(note))


@router.put("/notes/note")
async def update_note(
    request: Request,
    noteId: Optional[int] = None,
    note_id: Optional[int] = None,
    title: Optional[str] = None,
    content: Optional[str] = None,
    categoryId: Optional[int] = None,
    category_id: Optional[int] = None,
    coverImage: Optional[str] = None,
    cover_image: Optional[str] = None,
    isPublic: Optional[str] = None,
    is_public: Optional[str] = None,
    status: Optional[str] = None,
    markdownContent: Optional[str] = None,
    markdown_content: Optional[str] = None,
    tags: Optional[str] = None,
    publicSectionId: Optional[int] = None,
    public_section_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """更新笔记（仅本人可改）

    支持查询参数和 JSON body 两种传参方式。
    JSON body 字段：noteId（前端 editor.vue 传的是 id，已兼容）, title, content,
                    markdownContent, tags, publicSectionId, categoryId, coverImage, isPublic, status
    """
    # 兼容 JSON body 传参
    try:
        body = await request.json()
    except Exception:
        body = {}

    # 兼容前端 editor.vue 传的 id 写法
    nid = body.get("noteId") or body.get("note_id") or body.get("id") or noteId or note_id
    if not nid:
        return error("笔记ID不能为空", code=400)

    note, err = await _get_note_checked(db, nid, current_user)
    if err:
        return err

    # 合并查询参数与 body 字段(body 优先)
    title = body.get("title", title)
    content = body.get("content", content)
    markdown_content = body.get("markdownContent", body.get("markdown_content", markdownContent if markdownContent is not None else markdown_content))
    tags = body.get("tags", tags)
    public_section_id = body.get("publicSectionId", body.get("public_section_id", publicSectionId if publicSectionId is not None else public_section_id))
    category_id_val = body.get("categoryId", body.get("category_id", categoryId if categoryId is not None else category_id))
    cover_image_val = body.get("coverImage", body.get("cover_image", coverImage if coverImage is not None else cover_image))
    is_public_val = body.get("isPublic", body.get("is_public", isPublic if isPublic is not None else is_public))
    status_val = body.get("status", status)

    if title is not None:
        note.title = title
    if content is not None:
        note.content = content
    if markdown_content is not None:
        note.markdown_content = markdown_content
    if tags is not None:
        note.tags = tags
    if public_section_id is not None:
        note.public_section_id = public_section_id
    if category_id_val is not None:
        # 分类列 NOT NULL；改分类时同样要校验归属，避免挂到他人分类下
        cat = (await db.execute(
            select(NoteCategory).where(
                NoteCategory.id == category_id_val,
                NoteCategory.user_id == current_user.get("user_id"),
            )
        )).scalar_one_or_none()
        if not cat:
            return error("笔记分类不存在", code=400)
        note.category_id = category_id_val
    if cover_image_val is not None:
        note.cover_image = cover_image_val
    if is_public_val is not None:
        note.is_public = _int_flag(is_public_val)
    if status_val is not None:
        note.status = status_val

    note.update_time = datetime.now()

    return success()


@router.delete("/notes/note/{note_ids}")
async def delete_notes(
    note_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除笔记（逻辑删除，仅本人可删）"""
    user_id = current_user.get("user_id")
    ids = [int(id) for id in note_ids.split(",")]
    denied = await _deny_foreign_note_ids(db, ids, user_id)
    if denied:
        return denied
    stmt = update(Note).where(
        Note.note_id.in_(ids),
        Note.user_id == user_id,
    ).values(del_flag="2")
    await db.execute(stmt)

    return success()


@router.post("/notes/note/export")
async def export_notes(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """导出笔记列表为 Excel"""
    user_id = current_user.get("user_id")
    query = select(Note).where(
        Note.user_id == user_id,
        Note.del_flag == "0",
    ).order_by(Note.create_time.desc())

    result = await db.execute(query)
    notes_list = list(result.scalars().all())

    rows = [{
        "noteId": n.note_id,
        "title": n.title,
        "content": n.content[:200] if n.content else "",
        "isPublic": "是" if _int_flag(n.is_public) == 1 else "否",
        "viewCount": n.view_count,
        "likeCount": n.like_count,
        "commentCount": n.comment_count,
        "createTime": n.create_time.isoformat() if n.create_time else "",
    } for n in notes_list]

    headers = [
        {"key": "noteId", "label": "笔记ID"},
        {"key": "title", "label": "标题"},
        {"key": "content", "label": "内容摘要"},
        {"key": "isPublic", "label": "是否公开"},
        {"key": "viewCount", "label": "浏览数"},
        {"key": "likeCount", "label": "点赞数"},
        {"key": "commentCount", "label": "评论数"},
        {"key": "createTime", "label": "创建时间"},
    ]

    return export_to_excel(rows, headers, "note")


# ========== 笔记分类 API ==========

@router.get("/noteCategory/noteCategory/list")
async def list_categories(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询笔记分类列表"""
    user_id = current_user.get("user_id")
    query = select(NoteCategory).where(NoteCategory.user_id == user_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(NoteCategory.order_num.asc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    categories = list(result.scalars().all())

    return paginate(total, [format_category(c) for c in categories])


@router.get("/noteCategory/noteCategory/all")
async def list_all_categories(
    userId: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取所有笔记分类（仅本人；管理员可指定 userId）"""
    user_id, err = _resolve_user_scope(current_user, userId)
    if err:
        return err
    query = select(NoteCategory).where(NoteCategory.user_id == user_id).order_by(NoteCategory.order_num.asc())

    result = await db.execute(query)
    categories = list(result.scalars().all())

    return success([format_category(c) for c in categories])


@router.get("/noteCategory/noteCategory/{category_id}")
async def get_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询笔记分类详情（前端 getNoteCategory 使用的就是该路由）"""
    category = (await db.execute(
        select(NoteCategory).where(NoteCategory.id == category_id)
    )).scalar_one_or_none()
    if not category:
        return error("分类不存在")
    if int(category.user_id or 0) != int(current_user.get("user_id") or 0) and not _is_admin(current_user):
        return error("无权访问该分类", code=403)

    return success(format_category(category))


@router.post("/noteCategory/noteCategory")
async def create_category(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建笔记分类

    兼容三种字段写法：前端 editor.vue 传的是 name，后台管理页传 categoryName。
    """
    # 尝试从请求体获取数据
    try:
        body = await request.json()
    except:
        body = {}

    # 从查询参数或请求体获取数据
    name = body.get("name") or body.get("categoryName") or body.get("category_name")

    if not name:
        return error("分类名称不能为空", code=400)

    user_id = current_user.get("user_id")
    sort = (body.get("sortOrder") if body.get("sortOrder") is not None
            else body.get("sort_order", 0)) or 0

    category = NoteCategory(
        user_id=user_id,
        name=name,
        order_num=sort,
    )
    db.add(category)
    await db.flush()
    # create_time 是库端默认值，flush 后属性过期，直接序列化会触发同步懒加载 -> MissingGreenlet
    await db.refresh(category)

    return success(format_category(category))


@router.put("/noteCategory/noteCategory")
async def update_category(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """更新笔记分类（仅本人可改）"""
    try:
        body = await request.json()
    except:
        body = {}

    cid = body.get("categoryId") or body.get("category_id") or body.get("id")
    if not cid:
        return error("分类ID不能为空", code=400)

    query = select(NoteCategory).where(NoteCategory.id == cid)
    result = await db.execute(query)
    category = result.scalar_one_or_none()

    if not category:
        return error("分类不存在")

    if int(category.user_id or 0) != int(current_user.get("user_id") or 0):
        return error("无权修改他人的分类", code=403)

    name = body.get("name") or body.get("categoryName") or body.get("category_name")
    if name is not None:
        # 模型字段是 name（原实现写 category_name，属性不存在 → 静默不生效）
        category.name = name

    sort = body.get("orderNum")
    if sort is None:
        sort = body.get("sort_order")
    if sort is None:
        sort = body.get("sortOrder")
    if sort is not None:
        # 模型字段是 order_num（原实现写 sort_order，同样静默不生效）
        category.order_num = sort

    return success()


@router.delete("/noteCategory/noteCategory/{category_ids}")
async def delete_categories(
    category_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除笔记分类（仅本人可删）"""
    user_id = current_user.get("user_id")
    ids = [int(id) for id in category_ids.split(",")]
    denied = await _deny_foreign_category_ids(db, ids, user_id)
    if denied:
        return denied
    stmt = delete(NoteCategory).where(
        NoteCategory.id.in_(ids),
        NoteCategory.user_id == user_id,
    )
    await db.execute(stmt)

    return success()


# ========== 笔记评论 API ==========

@router.get("/notes/comment/list")
async def list_comments(
    noteId: int = Query(...),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查询笔记评论列表（仅一级评论）"""
    query = select(NoteComment).where(
        NoteComment.note_id == noteId,
        NoteComment.parent_id.is_(None),
        NoteComment.status == 0,
    )

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(NoteComment.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    comments = list(result.scalars().all())

    # 批量获取用户信息（包括回复目标用户）
    from app.models.user import SysUser
    user_ids = list(set(c.user_id for c in comments))
    # 收集所有 reply_to_user_id
    for c in comments:
        if c.reply_to_user_id:
            user_ids.append(c.reply_to_user_id)
    user_map = {}
    if user_ids:
        user_query = select(SysUser).where(SysUser.user_id.in_(user_ids))
        user_result = await db.execute(user_query)
        for user in user_result.scalars().all():
            user_map[user.user_id] = user

    # 统计每个评论的回复数
    comment_ids = [c.id for c in comments]
    reply_count_map = {}
    if comment_ids:
        reply_count_query = (
            select(NoteComment.parent_id, func.count())
            .where(NoteComment.parent_id.in_(comment_ids), NoteComment.status == 0)
            .group_by(NoteComment.parent_id)
        )
        reply_count_result = await db.execute(reply_count_query)
        for parent_id, count in reply_count_result.all():
            reply_count_map[parent_id] = count

    return success({
        "list": [
            {
                **format_comment(c, user_map.get(c.user_id), user_map.get(c.reply_to_user_id)),
                "replyCount": reply_count_map.get(c.id, 0),
            }
            for c in comments
        ],
        "total": total,
    })


@router.post("/notes/comment/create")
async def create_comment(
    noteId: int = Query(...),
    content: str = Query(...),
    parentId: Optional[int] = Query(None),
    replyToUserId: Optional[int] = Query(None),
    replyToUserName: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建评论"""
    user_id = current_user.get("user_id")

    # 笔记必须存在，否则评论表外键会直接抛 IntegrityError（500）
    note_query = select(Note).where(Note.note_id == noteId, Note.del_flag == "0")
    note = (await db.execute(note_query)).scalar_one_or_none()
    if not note:
        return error("笔记不存在", code=400)

    comment = NoteComment(
        note_id=noteId,
        user_id=user_id,
        content=content,
        parent_id=parentId,
        reply_to_user_id=replyToUserId,
    )
    db.add(comment)
    await db.flush()
    # create_time 为库端默认值，flush 后过期；不 refresh 直接序列化会触发
    # 同步懒加载 -> MissingGreenlet（原实现即因此 100% 返回 500）
    await db.refresh(comment)

    # 更新笔记评论数
    note.comment_count = (note.comment_count or 0) + 1
    db.add(note)

    # 发送评论通知（回复通知或一级评论通知）
    await _send_comment_notification(db, comment, note, user_id)

    # 获取当前用户和回复目标用户信息
    from app.models.user import SysUser
    user_ids = [user_id]
    if replyToUserId:
        user_ids.append(replyToUserId)
    user_query = select(SysUser).where(SysUser.user_id.in_(user_ids))
    user_result = await db.execute(user_query)
    user_map = {u.user_id: u for u in user_result.scalars().all()}

    return success(format_comment(comment, user_map.get(user_id), user_map.get(replyToUserId)))


async def _send_comment_notification(db: AsyncSession, comment, note, user_id: int):
    """发送评论通知：回复 / 一级评论 + 正文里 @ 到的人

    ⚠️ `mention` 此前只出现在 `notices.USER_NOTICE_TYPES` 白名单和前端标签里，
        **后端从未产生过** —— 用户被 @ 了收不到任何提醒，「回复与@」页永远缺这一类。
        这里补上：与主通知分开发，因为被 @ 的人通常不是被回复的那个人。

    ⚠️ 去重是必须的：一条评论可能既回复了 A、又 @ 了 A，
        不去重的话 A 会收到两条指向同一条评论的通知。
    """
    from app.models.notice import SysNotice
    import json
    import re

    content = comment.content or ""
    notice_content = content[:50] + "..." if len(content) > 50 else content

    # 本条评论已经通知过谁（起始含自己 —— 给自己发通知没有意义）
    notified = {int(user_id or 0)}

    def _build(target_user_id, ntype: str, title: str) -> None:
        target = int(target_user_id or 0)
        if not target or target in notified:
            return
        notified.add(target)
        db.add(SysNotice(
            notice_title=title,
            notice_content=notice_content,
            notice_type="1",
            status="0",
            create_by="system",
            remark=json.dumps({
                "type": ntype,
                "fromUserId": user_id,
                "toUserId": target,
                "noteId": comment.note_id,
                "commentId": comment.id,
            }, ensure_ascii=False),
        ))

    # ── 1) 主通知：回复 → 父评论作者；一级评论 → 笔记作者 ──
    if comment.parent_id:
        parent = (await db.execute(
            select(NoteComment).where(NoteComment.id == comment.parent_id)
        )).scalar_one_or_none()
        if parent:
            _build(parent.user_id, "reply", "有人回复了你")
    elif note:
        _build(note.user_id, "comment", "有人评论了你的笔记")

    # ── 2) @ 通知：正文里的 @{userId}（格式见 CommentInput.handleAtSelect） ──
    for uid in dict.fromkeys(re.findall(r"@\{(\d+)\}", content)):
        _build(uid, "mention", "有人 @了你")


@router.delete("/notes/comment/delete/{comment_id}")
async def delete_comment(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除评论（仅评论作者或笔记作者可删）"""
    comment = (await db.execute(
        select(NoteComment).where(NoteComment.id == comment_id)
    )).scalar_one_or_none()
    if not comment:
        return error("评论不存在")
    me = current_user.get("user_id")
    if int(comment.user_id or 0) != int(me or 0):
        # 笔记作者也可以删除自己笔记下的评论
        note = (await db.execute(
            select(Note).where(Note.note_id == comment.note_id)
        )).scalar_one_or_none()
        if not note or int(note.user_id or 0) != int(me or 0):
            return error("无权删除该评论", code=403)

    stmt = delete(NoteComment).where(NoteComment.id == comment_id)
    await db.execute(stmt)

    # 评论数必须跟着减，否则笔记列表上那个数字只会越删越大
    # （此前这条路径完全不碰 comment_count，是本功能暴露出来的既有缺口）。
    # ⚠️ 只减 1 —— 真删了几行就减几行。**刻意不级联删子留言**：
    #    子留言是别人写的，删一级评论时顺手把它们删掉属于破坏性行为，
    #    那个口径要不要改由人决定（现状是子留言留成看不见的孤儿，但仍占着计数）。
    note = (await db.execute(
        select(Note).where(Note.note_id == comment.note_id)
    )).scalar_one_or_none()
    if note:
        note.comment_count = max(0, (note.comment_count or 0) - 1)

    return success()


@router.get("/notes/comment/replies")
async def list_replies(
    parentId: int = Query(...),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查询评论的回复列表"""
    query = select(NoteComment).where(
        NoteComment.parent_id == parentId,
        NoteComment.status == 0,
    )

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(NoteComment.create_time.asc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    replies = list(result.scalars().all())

    # 批量获取用户信息（包括回复目标用户）
    from app.models.user import SysUser
    user_ids = list(set(c.user_id for c in replies))
    # 收集所有 reply_to_user_id
    for c in replies:
        if c.reply_to_user_id:
            user_ids.append(c.reply_to_user_id)
    user_map = {}
    if user_ids:
        user_query = select(SysUser).where(SysUser.user_id.in_(user_ids))
        user_result = await db.execute(user_query)
        for user in user_result.scalars().all():
            user_map[user.user_id] = user

    return success({
        "list": [format_comment(c, user_map.get(c.user_id), user_map.get(c.reply_to_user_id)) for c in replies],
        "total": total,
    })


@router.get("/notes/comment/thread/{comment_id}")
async def get_comment_thread(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取评论及其所有回复（完整评论树）"""
    logger.info(f"[评论跳转] 获取评论线程 comment_id={comment_id}")
    # 获取主评论
    query = select(NoteComment).where(
        NoteComment.id == comment_id,
        NoteComment.status == 0,
    )
    result = await db.execute(query)
    comment = result.scalar_one_or_none()

    if not comment:
        return error("评论不存在")

    # 批量获取用户信息
    from app.models.user import SysUser
    user_ids = list(set([comment.user_id]))
    # 收集顶级评论的 reply_to_user_id
    if comment.reply_to_user_id:
        user_ids.append(comment.reply_to_user_id)
    user_map = {}
    if user_ids:
        user_query = select(SysUser).where(SysUser.user_id.in_(user_ids))
        user_result = await db.execute(user_query)
        for user in user_result.scalars().all():
            user_map[user.user_id] = user

    # 统计所有子回复数
    all_comment_ids = [comment.id]
    async def collect_all_ids(parent_id):
        reply_query = select(NoteComment.id).where(
            NoteComment.parent_id == parent_id,
            NoteComment.status == 0,
        )
        reply_result = await db.execute(reply_query)
        ids = [row[0] for row in reply_result.all()]
        all_comment_ids.extend(ids)
        for cid in ids:
            await collect_all_ids(cid)
    await collect_all_ids(comment.id)
    
    reply_count_map = {}
    if all_comment_ids:
        reply_count_query = (
            select(NoteComment.parent_id, func.count())
            .where(NoteComment.parent_id.in_(all_comment_ids), NoteComment.status == 0)
            .group_by(NoteComment.parent_id)
        )
        reply_count_result = await db.execute(reply_count_query)
        for parent_id, count in reply_count_result.all():
            reply_count_map[parent_id] = count

    # 递归构建评论树
    async def build_comment_tree(parent_id):
        reply_query = select(NoteComment).where(
            NoteComment.parent_id == parent_id,
            NoteComment.status == 0,
        ).order_by(NoteComment.create_time.asc())
        reply_result = await db.execute(reply_query)
        replies = list(reply_result.scalars().all())

        # 收集用户ID
        for r in replies:
            if r.user_id not in user_map:
                user_ids.append(r.user_id)
            if r.reply_to_user_id and r.reply_to_user_id not in user_map:
                user_ids.append(r.reply_to_user_id)

        if user_ids:
            user_query = select(SysUser).where(SysUser.user_id.in_(user_ids))
            user_result = await db.execute(user_query)
            for user in user_result.scalars().all():
                user_map[user.user_id] = user

        result = []
        for r in replies:
            reply_data = format_comment(r, user_map.get(r.user_id), user_map.get(r.reply_to_user_id))
            reply_data["replyCount"] = reply_count_map.get(r.id, 0)
            reply_data["children"] = await build_comment_tree(r.id)
            result.append(reply_data)
        return result

    comment_data = format_comment(comment, user_map.get(comment.user_id), user_map.get(comment.reply_to_user_id))
    comment_data["replyCount"] = reply_count_map.get(comment.id, 0)
    comment_data["children"] = await build_comment_tree(comment.id)

    return success(comment_data)


# ========== 收藏笔记 API ==========

@router.get("/favoriteNote/favoriteNote/list")
async def list_favorite_notes(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询收藏笔记列表"""
    from app.models.note import UserNoteFavorite

    user_id = current_user.get("user_id")
    # ⚠️ 列表与下面的 `total` **必须由同一条 query 派生**（total 就是从它 count 出来的）。
    #    此前只查 `user_note_favorite`、一条 `del_flag` 条件都没有：
    #      · 已软删的笔记照样出现在收藏列表里（点进去 404）；
    #      · `total` 把已删的也算进去 → 「分页总数 > 实际返回行数」，翻到最后一页是空的。
    #    口径用 `note.del_flag`（'0' = 未删、'2' = 已删），与同文件其它列表一致
    #    （写点见 `services/note_write_service.py:465`），不另发明第二套。
    query = (
        select(UserNoteFavorite)
        .join(Note, Note.note_id == UserNoteFavorite.note_id)
        .where(
            UserNoteFavorite.user_id == user_id,
            Note.del_flag == "0",
        )
    )

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(UserNoteFavorite.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    favorites = list(result.scalars().all())

    rows = []
    for fav in favorites:
        # 同一条口径再落一次：上面的 join 已经把已删的挡住了，这里是防「取到之后被删」
        # （两个查询之间没有事务级快照保证），也保持「读笔记必带 del_flag」的既有写法。
        note_query = select(Note).where(
            Note.note_id == fav.note_id, Note.del_flag == "0"
        )
        note_result = await db.execute(note_query)
        note = note_result.scalar_one_or_none()
        if note:
            row = format_note(note)
            row["favoriteId"] = fav.favorite_id
            rows.append(row)

    return paginate(total, rows)


@router.post("/favoriteNote/favoriteNote")
async def add_favorite_note(
    noteId: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """收藏笔记"""
    from app.models.note import UserNoteFavorite

    user_id = current_user.get("user_id")

    check_query = select(UserNoteFavorite).where(
        UserNoteFavorite.user_id == user_id,
        UserNoteFavorite.note_id == noteId,
    )
    check_result = await db.execute(check_query)
    if check_result.scalar_one_or_none():
        return error("已收藏该笔记", code=400)

    favorite = UserNoteFavorite(user_id=user_id, note_id=noteId)
    db.add(favorite)

    return success()


@router.delete("/favoriteNote/favoriteNote/{ids}")
async def delete_favorite_notes(
    ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """取消收藏笔记（按 favorite_id）"""
    from app.models.note import UserNoteFavorite

    id_list = [int(id) for id in ids.split(",")]
    stmt = delete(UserNoteFavorite).where(
        UserNoteFavorite.favorite_id.in_(id_list),
        UserNoteFavorite.user_id == current_user.get("user_id")
    )
    await db.execute(stmt)

    return success()


@router.delete("/favoriteNote/favoriteNote/deleteByUserAndNote/{userId}/{noteId}")
async def delete_favorite_note_by_user_and_note(
    userId: int,
    noteId: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """取消收藏笔记（按 userId + noteId）"""
    from app.models.note import UserNoteFavorite

    # 只能取消自己的收藏
    if userId != current_user.get("user_id"):
        return error("无权操作他人的收藏", code=403)

    stmt = delete(UserNoteFavorite).where(
        UserNoteFavorite.user_id == userId,
        UserNoteFavorite.note_id == noteId
    )
    await db.execute(stmt)

    return success()


# ========== 笔记分区 API ==========

@router.get("/notes/note/publicSection/list")
async def list_public_sections(
    db: AsyncSession = Depends(get_db),
):
    """获取笔记分区列表"""
    from sqlalchemy import text
    result = await db.execute(text("SELECT id, name, sort_order FROM note_public_section ORDER BY sort_order"))
    sections = []
    for row in result:
        sections.append({
            "id": row[0],
            "name": row[1],
            "icon": None,
            "sortOrder": row[2],
        })
    return success(sections)


# ========== 用户「笔记草稿」API（智能体与前端共用） ==========
# ⚠️ 这是「写笔记」页的**临时草稿**（用户维度、无 noteId、不进笔记列表），
#    与 note 表里 status='draft' 的正式笔记是两回事（用户 2026-10-11 报的语义混淆）。

@router.get("/notes/note/draft")
async def get_note_draft(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """取当前用户的后端草稿（没有则 data=null）"""
    from app.services import note_draft_service as nds
    uid = current_user.get("user_id")
    draft = await nds.get_draft(db, int(uid))
    return success(nds.draft_to_dict(draft))


@router.put("/notes/note/draft")
async def save_note_draft(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """保存/更新当前用户的后端草稿（前端「写笔记」自动保存时同步）"""
    from app.services import note_draft_service as nds
    uid = int(current_user.get("user_id"))
    body = await request.json()
    draft = await nds.upsert_draft(
        db,
        uid,
        title=body.get("title"),
        content=body.get("content"),
        markdown_content=body.get("markdownContent", body.get("markdown_content")),
        category_id=body.get("categoryId", body.get("category_id")),
        tags=body.get("tags"),
        is_public=body.get("isPublic", body.get("is_public")),
        public_section_id=body.get("publicSectionId", body.get("public_section_id")),
    )
    return success(nds.draft_to_dict(draft))


@router.delete("/notes/note/draft")
async def clear_note_draft(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """清除当前用户的后端草稿（发布成功 / 用户丢弃时）"""
    from app.services import note_draft_service as nds
    uid = int(current_user.get("user_id"))
    n = await nds.clear_draft(db, uid)
    return success({"deleted": n})
