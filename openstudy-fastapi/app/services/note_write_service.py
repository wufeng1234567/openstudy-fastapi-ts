"""
`note_write_service` —— 笔记域的读写服务

为什么单独一层而不是把逻辑写进 `note_manage` 工具里：
对齐 `question_write_service` —— 库结构的坑（NOT NULL 兜底、逻辑删除、字段 refresh）
集中在一处，工具层只管「参数校验 + 人话回执」。将来 `api/v1/notes.py` 想复用也能直接调。

⚠️ 四个库结构遗留坑（SpringBoot 迁移留下的，Agent 一接就全踩）：

1. **`note.category_id` 是 NOT NULL**，外键指向 `note_category`，而分类是**按用户隔离**的。
   ⇒ 一个用户如果一条分类都没建过，就**根本建不出笔记** —— `api/v1/notes.py:635`
   直接回「请先选择笔记分类」。Agent 场景里用户不会先去自己建分类，
   所以 `resolve_category()` 在没给分类时**兜底建一个「默认分类」**。
   （否则最常见的「帮我把这段记成笔记」会 100% 失败。）
2. **`note.filename` 是 NOT NULL**（SpringBoot 遗留列，无有效默认值）。
   ⇒ 建 `Note` 时必须显式给值，否则 `IntegrityError` 变成 500 服务器内部错误。
3. **`create_time` / `update_time` 走库端默认值**，`flush()` 后属性被标记为过期。
   ⇒ 必须 `await db.refresh(note)` 再同步读，否则触发懒加载 -> `MissingGreenlet`。
   （`api/v1/notes.py:664-666` 有同样的注释，是同一个坑。）
4. **`is_public` 的语义和题库相反**：笔记是 **1=公开 / 0=私密**
   （`api/v1/notes.py:291` 查公开笔记用 `is_public == 1` 佐证），
   而题库是 **0=公开 / 1=私密**（`api/v1/questions.py:417`）。
   因此 `note_brief()` 故意**不回 `isPublic`**，改回人话字段 `visibility`
   —— 理由见该函数内的注释，别改回去。

删除一律是**逻辑删除**（`del_flag="2"`，对齐 `api/v1/notes.py:770`）。
所以所有读查询都必须带 `del_flag == "0"`，否则会把已删的笔记再查出来。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note, NoteCategory
from app.services.ai.agent.base import fail

#: 没分类时自动创建的分类名（见模块 docstring 的坑 1）
DEFAULT_CATEGORY_NAME = "默认分类"

#: `note.status` 只认这两个值（`api/v1/notes.py` 建笔记时默认 draft，前端按 draft/published 渲染）
NOTE_STATUSES = ("draft", "published")

#: status → 人话。跟 `question_write_service.QUESTION_TYPE_TEXT` 一个思路：
#: 标识符对用户没意义。**故意不走前端的全局 ENUM_LABELS** —— `status` 这个键名
#: 太通用，题库的 `status` 是 '0'/'1' 另一套语义，共用一张枚举表必然互相打架。
STATUS_TEXT = {"draft": "草稿", "published": "已发布"}

#: `note.tags` 是 varchar(500)，超长会被库直接拒绝
TAGS_MAX = 500

#: 列表类结果最多返回多少篇（Agent 回灌给模型的内容要有上限，全量会撑爆上下文）
LIST_LIMIT = 20


# ----------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _split_multi(value: Any) -> List[str]:
    """把「单个值 / 数组 / JSON 字符串 / 逗号串」统一成字符串列表

    模型的入参形态不总是规范（`"a,b"` / `'["a","b"]'` / `["a"]` 都可能），
    本地实现一份而不是复用 `agent.base.as_list` —— 避免服务层反向依赖 agent 层。
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        import json

        try:
            parsed = json.loads(text)
        except Exception:  # noqa: BLE001 - 解析不了就退回逗号分隔
            parsed = None
        if isinstance(parsed, list):
            return [str(v).strip() for v in parsed if str(v).strip()]
    return [p.strip() for p in text.replace("，", ",").split(",") if p.strip()]


def normalize_tags(value: Any) -> Optional[str]:
    """标签归一成逗号分隔字符串；空输入返回 `None`（保持库里的 NULL 语义）"""
    parts = _split_multi(value)
    if not parts:
        return None
    # 去重且保持原顺序 —— 重复标签对用户没意义
    seen: set = set()
    uniq: List[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return ",".join(uniq)[:TAGS_MAX]


def _fmt_time(value: Optional[datetime]) -> Optional[str]:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


# ----------------------------------------------------------------------
# 输出格式化
# ----------------------------------------------------------------------


def note_brief(note: Note, *, with_preview: bool = True) -> Dict[str, Any]:
    """笔记摘要（Agent / 提示词统一用它，字段名保持 camelCase 以免前端再转）

    ⚠️ **故意不回 `isPublic`，改用 `visibility`**（别「顺手对齐题库」改回去）：

      · 题库 `is_public`：0=公开 / 1=私密（`api/v1/questions.py:417`）
      · 笔记 `is_public`：**1=公开 / 0=私密**（`api/v1/notes.py:291`）

    前端 `AgentToolDetail` 的 `ENUM_LABELS.isPublic` 是**按题库语义写的全局映射**
    （`{'0':'公开','1':'私密'}`），并不区分工具。笔记若照回 `isPublic`，
    可见性会**显示成反的** —— 用户看到「私密」的其实是公开笔记。
    所以这里直接给人话，前端只需补一个 `visibility` 的字段标签即可，不必动那个共享枚举。
    """
    data: Dict[str, Any] = {
        "noteId": note.note_id,
        "title": note.title,
        "categoryId": note.category_id,
        "visibility": "公开" if int(note.is_public or 0) == 1 else "私密",
        "status": note.status,
        # 人话状态（前端按 `statusText` 存在与否隐藏原始 `status`，同 questionTypeText 的做法）
        "statusText": STATUS_TEXT.get(str(note.status or ""), str(note.status or "")),
        "tags": note.tags or "",
        "createTime": _fmt_time(note.create_time),
        "updateTime": _fmt_time(note.update_time),
    }
    if with_preview:
        # 列表里只给正文开头 —— 整篇回灌给模型既费 token 也没必要
        body = note.content or note.markdown_content or ""
        data["contentLength"] = len(body)
        data["contentPreview"] = body[:80] + ("…" if len(body) > 80 else "")
    return data


def note_detail(note: Note) -> Dict[str, Any]:
    """笔记详情（带完整正文，供 `detail` / `update` 回执用）"""
    data = note_brief(note, with_preview=False)
    # content 与 markdownContent 互相兜底（口径同 `api/v1/notes.py:format_note`，见那处注释）
    data["content"] = note.content or note.markdown_content
    data["markdownContent"] = note.markdown_content or note.content
    data["coverImage"] = note.cover_image
    data["contentLength"] = len(note.content or note.markdown_content or "")
    return data


# ----------------------------------------------------------------------
# 查询
# ----------------------------------------------------------------------


async def list_user_notes(
    db: AsyncSession,
    user_id: int,
    *,
    keyword: Optional[str] = None,
    category_id: Optional[int] = None,
    limit: int = LIST_LIMIT,
) -> Tuple[List[Note], int]:
    """列出用户自己的笔记（可按标题/正文模糊、分类过滤）

    Returns:
        (本页笔记, 总条数) —— 两个都给，模型才能说对「共 N 篇，本次返回 M 篇」
    """
    from sqlalchemy import func, or_

    query = select(Note).where(Note.user_id == user_id, Note.del_flag == "0")

    text = (keyword or "").strip()
    if text:
        # 标题、正文、markdown、标签都搜 —— 用户说「那篇讲牛顿定律的」时命中率更高
        like = f"%{text}%"
        query = query.where(
            or_(
                Note.title.like(like),
                Note.content.like(like),
                Note.markdown_content.like(like),
                Note.tags.like(like),
            )
        )
    if category_id is not None:
        query = query.where(Note.category_id == int(category_id))

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0

    query = query.order_by(Note.create_time.desc(), Note.note_id.desc())
    if limit > 0:
        query = query.limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all()), int(total)


async def get_user_note(
    db: AsyncSession, user_id: int, note_id: Any
) -> Optional[Note]:
    """按 ID 取**自己的、未删除的**笔记；取不到返回 None"""
    nid = _to_int(note_id)
    if nid is None:
        return None
    result = await db.execute(
        select(Note).where(
            Note.note_id == nid,
            Note.user_id == user_id,
            Note.del_flag == "0",
        )
    )
    return result.scalars().first()


async def find_notes_by_title(
    db: AsyncSession, user_id: int, title: str, *, limit: int = 5
) -> List[Note]:
    """按标题**模糊**查（笔记标题不唯一，所以只用来给模型候选，不做定位依据）"""
    text = (title or "").strip()
    if not text:
        return []
    result = await db.execute(
        select(Note)
        .where(
            Note.user_id == user_id,
            Note.del_flag == "0",
            Note.title.like(f"%{text}%"),
        )
        .order_by(Note.create_time.desc(), Note.note_id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_user_categories(
    db: AsyncSession, user_id: int
) -> List[NoteCategory]:
    """用户自己的笔记分类（按排序号、再按 id 稳定排序）"""
    result = await db.execute(
        select(NoteCategory)
        .where(NoteCategory.user_id == user_id)
        .order_by(NoteCategory.order_num.asc(), NoteCategory.id.asc())
    )
    return list(result.scalars().all())


async def find_category_by_name(
    db: AsyncSession, user_id: int, name: str
) -> Optional[NoteCategory]:
    """按名**精确**查用户自己的分类；查不到或名为空返回 None

    库里 `note_category.name` **没有唯一约束**（见 `api/v1/notes.py:943`），
    所以「有没有重名」只能靠这里先查一遍 —— `create_category` 的幂等都建立在它之上。
    """
    text = (name or "").strip()
    if not text:
        return None
    result = await db.execute(
        select(NoteCategory).where(
            NoteCategory.user_id == user_id, NoteCategory.name == text
        )
    )
    return result.scalars().first()


async def create_category(
    db: AsyncSession,
    user_id: int,
    name: str,
    order_num: Any = 0,
) -> NoteCategory:
    """创建笔记分类（**幂等**：同名分类已存在则直接返回它，不建重复）

    名称在库里没有唯一约束，所以先 `find_category_by_name` 再决定建不建。
    与 `api/v1/notes.py:943` 的同名接口同口径：insert + flush + refresh
    （坑 3：不 refresh 就同步读 create_time 会 MissingGreenlet）。

    ⚠️ 调用方需先校验名称非空 —— 这里只在空名时抛 `ValueError`。
    """
    text = (name or "").strip()
    if not text:
        raise ValueError("分类名不能为空")
    existing = await find_category_by_name(db, user_id, text)
    if existing is not None:
        return existing
    cat = NoteCategory(user_id=user_id, name=text, order_num=_to_int(order_num) or 0)
    db.add(cat)
    await db.flush()
    # 坑 3：create_time 是库端默认值，不 refresh 就同步读会 MissingGreenlet
    await db.refresh(cat)
    return cat


# ----------------------------------------------------------------------
# 分类兜底（坑 1）
# ----------------------------------------------------------------------


async def resolve_category(
    db: AsyncSession,
    user_id: int,
    *,
    category_id: Any = None,
    category_name: Optional[str] = None,
) -> Tuple[Optional[NoteCategory], Optional[Dict[str, Any]]]:
    """定位要用的笔记分类

    优先级：`category_id` → `category_name` → 用户的第一个分类 → **自动建「默认分类」**。

    最后一档是必须的：`note.category_id` 是 NOT NULL，用户一条分类都没有时
    建笔记 100% 失败（见模块 docstring 的坑 1）。

    Returns:
        `(NoteCategory, None)` 成功；`(None, fail信封)` 失败
    """
    if category_id is not None:
        cid = _to_int(category_id)
        if cid is None:
            return None, fail(
                f"category_id 不是合法整数：{category_id}",
                "请传整数分类 ID，或者改用 category_name",
            )
        cat = (
            await db.execute(
                select(NoteCategory).where(
                    NoteCategory.id == cid, NoteCategory.user_id == user_id
                )
            )
        ).scalars().first()
        if cat is None:
            return None, fail(
                f"笔记分类不存在或不属于你：category_id={cid}",
                "请先用 action=list_categories 查看自己的分类",
            )
        return cat, None

    name = (category_name or "").strip()
    if name:
        cat = await find_category_by_name(db, user_id, name)
        if cat is not None:
            return cat, None
        existing = await list_user_categories(db, user_id)
        names = "、".join(c.name for c in existing[:8]) or "（还没有任何分类）"
        return None, fail(
            f"没有名为「{name}」的笔记分类",
            f"名称需要完全一致。你现有的分类：{names}。"
            f"也可以省略 category_name，会自动放进「{DEFAULT_CATEGORY_NAME}」",
        )

    existing = await list_user_categories(db, user_id)
    if existing:
        return existing[0], None

    cat = NoteCategory(user_id=user_id, name=DEFAULT_CATEGORY_NAME, order_num=0)
    db.add(cat)
    await db.flush()
    # 坑 3：create_time 是库端默认值，不 refresh 就同步读会 MissingGreenlet
    await db.refresh(cat)
    return cat, None


# ----------------------------------------------------------------------
# 写操作
# ----------------------------------------------------------------------


async def create_note(
    db: AsyncSession,
    user_id: int,
    *,
    title: str,
    category: NoteCategory,
    content: Optional[str] = None,
    markdown_content: Optional[str] = None,
    tags: Any = None,
    cover_image: Optional[str] = None,
    is_public: Any = 0,
    status: Optional[str] = None,
) -> Note:
    """建笔记（调用方需先用 `resolve_category` 拿到分类）"""
    # ⚠️ content 与 markdown_content **互相兜底**（用户 2026-10-11 报的"Agent 建的笔记在
    #    个人中心/详情页空白"真因）：前端所有笔记展示（详情页 `notes/detail.vue`、列表
    #    `myNotes`/`notes/list`、编辑器 `notesEditor`/`editor`）**只读 `markdownContent`**，
    #    而 Agent 工具（`note_manage._create`）允许只传 `content`。若只落 `content`，
    #    前端读 `markdownContent` 就是空的 → 一片空白。故落库时把两者补齐成一致：
    #    · 只给 content        → markdown_content 也填 content（纯文本，md 渲染器照样能显示）
    #    · 只给 markdown_content → content 也填它
    #    （纯文本塞进 md 字段安全：markdown 是纯文本的超集，`\n` 也正常。）
    if content and not markdown_content:
        markdown_content = content
    elif markdown_content and not content:
        content = markdown_content
    note = Note(
        user_id=user_id,
        category_id=category.id,
        title=title.strip(),
        # 坑 2：filename 是 NOT NULL 的 SpringBoot 遗留列，不给值会 IntegrityError -> 500
        filename="",
        content=content,
        markdown_content=markdown_content,
        tags=normalize_tags(tags),
        cover_image=cover_image,
        # 坑 4：笔记 1=公开 / 0=私密（与题库相反）
        is_public=1 if _to_int(is_public) == 1 else 0,
        status=normalize_status(status) or "draft",
    )
    db.add(note)
    await db.flush()
    # 坑 3：不 refresh 就同步读 create_time 会触发懒加载 -> MissingGreenlet
    await db.refresh(note)
    return note


def normalize_status(value: Optional[str]) -> Optional[str]:
    """把 status 收敛到合法值；给的值不认识时返回 None（由调用方决定兜底）"""
    text = (value or "").strip().lower()
    return text if text in NOTE_STATUSES else None


async def update_note(
    db: AsyncSession,
    note: Note,
    *,
    title: Optional[str] = None,
    content: Optional[str] = None,
    markdown_content: Optional[str] = None,
    tags: Any = None,
    category: Optional[NoteCategory] = None,
    is_public: Any = None,
    status: Optional[str] = None,
) -> List[str]:
    """按「给了才改」的方式更新笔记，返回被改动的字段名列表

    `content` / `markdown_content` 用 `is not None` 判断而不是真值判断 ——
    清空正文是合法操作，`if content:` 会把「改成空」静默吞掉。
    """
    changed: List[str] = []

    if title is not None and title.strip():
        note.title = title.strip()
        changed.append("title")
    if content is not None:
        note.content = content
        changed.append("content")
    if markdown_content is not None:
        note.markdown_content = markdown_content
        changed.append("markdown_content")
    if tags is not None:
        note.tags = normalize_tags(tags)
        changed.append("tags")
    if category is not None:
        note.category_id = category.id
        changed.append("category_id")
    if is_public is not None:
        note.is_public = 1 if _to_int(is_public) == 1 else 0
        changed.append("is_public")
    if status is not None:
        note.status = status
        changed.append("status")

    if changed:
        note.update_time = datetime.now()
        await db.flush()
        await db.refresh(note)
    return changed


async def delete_notes(
    db: AsyncSession, user_id: int, note_ids: Iterable[Any]
) -> Dict[str, Any]:
    """删除笔记（**逻辑删除**，只允许删自己的）

    与 `api/v1/notes.py:770` 的 `del_flag="2"` 保持一致 —— 不物理删，
    免得连带破坏 note_question 关联和公开笔记的评论。

    Returns:
        {"deleted": [{"noteId":..,"title":..}], "missing": [id, ...]}
    """
    ids: List[int] = []
    for value in note_ids:
        nid = _to_int(value)
        if nid is not None and nid not in ids:
            ids.append(nid)
    if not ids:
        return {"deleted": [], "missing": []}

    # 只取「属于当前用户且未删除」的（标量列 → 不加载 ORM 对象）
    rows = (
        await db.execute(
            select(Note.note_id, Note.title).where(
                Note.note_id.in_(ids),
                Note.user_id == user_id,
                Note.del_flag == "0",
            )
        )
    ).all()

    own_ids = [int(r[0]) for r in rows]
    deleted = [{"noteId": int(r[0]), "title": r[1]} for r in rows]
    own_set = set(own_ids)
    missing = [i for i in ids if i not in own_set]

    if own_ids:
        await db.execute(
            update(Note)
            .where(Note.note_id.in_(own_ids), Note.user_id == user_id)
            .values(del_flag="2", update_time=datetime.now())
        )
    return {"deleted": deleted, "missing": missing}


__all__ = [
    "DEFAULT_CATEGORY_NAME",
    "NOTE_STATUSES",
    "STATUS_TEXT",
    "LIST_LIMIT",
    "note_brief",
    "note_detail",
    "normalize_tags",
    "normalize_status",
    "list_user_notes",
    "get_user_note",
    "find_notes_by_title",
    "list_user_categories",
    "find_category_by_name",
    "create_category",
    "resolve_category",
    "create_note",
    "update_note",
    "delete_notes",
]
