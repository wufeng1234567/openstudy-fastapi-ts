"""
错题本 / 收藏 / 斩题 —— 三类「个人题目标记」记录的领域服务

三张表的形状几乎一样（`user_id` + `question_id` + `bank_id` + 一个状态位 + notes/tags），
但**语义完全不同**，所以工具层拆成三个工具（`tools/question_mark_manage.py`），
领域逻辑在这里收一份。

语义来源（**照抄既有 API，不另造一套**）
----------------------------------------
· 错题本 `user_question_error`
    - 日常由 `POST /questionPractice/report`（答错时）自动 upsert（`api/v1/questions.py:1129`）
    - `status=1` = 活跃在错题本里；`is_mastered=1 + status=0` = 已掌握
      （`POST /questionError/questionError/markMastered`，`questions.py:2974`）
    - **已掌握后再答错会被 report 重新激活**（`status=1, is_mastered=0`）
· 收藏 `user_question_favorite`
    - `favorite_status=1` 有效；「取消收藏」= **物理删**该行（`questions.py:2508`）
· 斩题 `user_question_marked`
    - `marked_status=1` 有效；「取消斩题」= **物理删**该行（`questions.py:3553`）
    - `marked_type`：1 错题 / 2 难题 / 3 重点 / 4 易错 / 5 技巧（`questions.py:378`）

⚠️⚠️ **每一处「按 id 定位」都带 `user_id` 条件**（`_OWNED_*` 系列）。
三张表的主键是全局自增：只按 id 取 = 任何登录用户拿别人的 id 就能读/删别人的记录
（这正是 `question_manage` / `bank_manage` 已经踩过、本轮要修的那类越权）。
查不到时一律当「不存在」处理，**不区分**「不存在」与「不是你的」——
区分开就等于给对方一个探测他人记录是否存在的接口。

⚠️ 本模块**只 `flush()`，从不 `commit()`**（与 `question_write_service` / `note_write_service`
同一约定）：调用方可能是 `loop._execute_tool` 里那个 SAVEPOINT。
`commit()` 会把 SAVEPOINT 连同外层事务一起提交掉，退出时抛
`Can't operate on closed transaction inside context manager`
（实测见 `tests/_probe_nested_commit.py`）—— 而且是**数据已写、用户却看到失败**。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_share import BankShareReceive
from app.models.question import (
    QuestionBank,
    QuestionMain,
    UserQuestionError,
    UserQuestionFavorite,
    UserQuestionMarked,
)

#: 三类记录
KIND_ERROR = "error"
KIND_FAVORITE = "favorite"
KIND_MARKED = "marked"

#: 斩题类型（与 `api/v1/questions.py:_get_marked_type_text` 同一张表）
MARKED_TYPE_TEXT: Dict[int, str] = {
    1: "错题",
    2: "难题",
    3: "重点",
    4: "易错",
    5: "技巧",
}

#: 一页最多几条（与 `question_manage` 的 limit 量级一致）
MAX_LIMIT = 50
DEFAULT_LIMIT = 20


class _Kind:
    """一类记录的「表 + 列 + 文案」。

    只做参数化，不做继承 —— 三类记录的差别就是这几个列名，别的都一样。
    """

    def __init__(
        self,
        *,
        kind: str,
        label: str,
        model: Any,
        id_column: Any,
        id_key: str,
        status_column: Any,
        order_column: Any,
    ) -> None:
        self.kind = kind
        self.label = label
        self.model = model
        self.id_column = id_column
        self.id_key = id_key  # 对外字段名（errorId / favoriteId / markedId）
        self.status_column = status_column
        self.order_column = order_column


KINDS: Dict[str, _Kind] = {
    KIND_ERROR: _Kind(
        kind=KIND_ERROR,
        label="错题",
        model=UserQuestionError,
        id_column=UserQuestionError.error_id,
        id_key="errorId",
        status_column=UserQuestionError.status,
        # 错题列表 API 按「最近出错时间」排（questions.py:2807），照抄
        order_column=UserQuestionError.last_error_time,
    ),
    KIND_FAVORITE: _Kind(
        kind=KIND_FAVORITE,
        label="收藏",
        model=UserQuestionFavorite,
        id_column=UserQuestionFavorite.favorite_id,
        id_key="favoriteId",
        status_column=UserQuestionFavorite.favorite_status,
        order_column=UserQuestionFavorite.create_time,
    ),
    KIND_MARKED: _Kind(
        kind=KIND_MARKED,
        label="斩题",
        model=UserQuestionMarked,
        id_column=UserQuestionMarked.marked_id,
        id_key="markedId",
        status_column=UserQuestionMarked.marked_status,
        order_column=UserQuestionMarked.create_time,
    ),
}


def kind_spec(kind: str) -> Optional[_Kind]:
    return KINDS.get(kind)


# ---------------------------------------------------------------- 题库可见性


async def shared_bank_ids(db: AsyncSession, user_id: int) -> set:
    """通过「领取分享」拿到的题库 id 集合（含已失效 —— 与 questions.py:406 同口径）"""
    if not user_id:
        return set()
    rows = (
        await db.execute(
            select(BankShareReceive.bank_id).where(BankShareReceive.receiver_id == user_id)
        )
    ).all()
    return {r[0] for r in rows}


async def can_view_bank(db: AsyncSession, user_id: int, bank: QuestionBank) -> bool:
    """题库可见性（与 `api/v1/questions.py:_can_view_bank` 同一套判定）

    公开题库（`is_public=0`，**注意 0 才是公开**）任何人可看；私密题库只有题库主
    与「领取过分享」的人可看。
    """
    if bank is None:
        return False
    if not bank.is_public:
        return True
    if bank.user_id == user_id:
        return True
    return bank.id in await shared_bank_ids(db, user_id)


async def resolve_visible_question(
    db: AsyncSession, user_id: int, question_id: Any
) -> Tuple[Optional[QuestionMain], Optional[QuestionBank], Optional[str]]:
    """按 id 取题目，并校验「这个用户能不能看见它」。

    Returns: `(question, bank, err)`；`err` 非空时前两个都是 None。

    ⚠️ 为什么**写自己名下的记录**也要校验可见性：`user_question_*` 表只按
    `question_id` 关联，题目 id 是全局自增的。不校验的话，模型（或用户）拿一个
    别人的私密题目 id 就能在自己名下造一条指向它的记录，进而读到它的题干
    —— 那不是「写自己的数据」，那是**借自己的账号读别人的数据**。
    既有 API（`POST /favoriteQuestion`）只判「题目是否存在」，这里刻意更严一档：
    Agent 的入参是模型生成的 id，比人手点的按钮更容易乱指。
    """
    try:
        qid = int(question_id)
    except (TypeError, ValueError):
        return None, None, f"题目 ID 无法识别：{question_id}"

    question = await db.get(QuestionMain, qid)
    if question is None:
        return None, None, f"题目不存在：question_id={qid}"

    bank = await db.get(QuestionBank, int(question.bank_id))
    if bank is None:
        return None, None, f"题目所属题库不存在（bank_id={question.bank_id}）"

    if not await can_view_bank(db, user_id, bank):
        return None, None, f"题目 {qid} 所属的题库「{bank.bank_name}」不在你可以访问的范围内"
    return question, bank, None


# ---------------------------------------------------------------- 查询


def _active_condition(spec: _Kind, active_only: bool) -> List[Any]:
    if not active_only:
        return []
    if spec.kind == KIND_ERROR:
        # 错题本的「活跃」= status=1（已掌握的会被置 0），与列表 API 同口径
        return [spec.status_column == 1]
    return [spec.status_column == 1]


async def list_records(
    db: AsyncSession,
    user_id: int,
    kind: str,
    *,
    bank_id: Optional[int] = None,
    keyword: Optional[str] = None,
    active_only: bool = True,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
) -> Tuple[List[Tuple[Any, QuestionMain, Optional[str]]], int]:
    """列出一类记录（JOIN 题目表拿题干），返回 `(rows, total)`。

    rows = `[(record, question, bank_name), ...]`。
    `total` 是**过滤后的命中总量**，不是本页条数 —— 只回一页却说成总数，
    模型会把「本次返回 20 条」讲成「一共 20 条」。

    关键词只在**题干**上模糊匹配（`user_question_*` 表本身没有题干，
    与前端「我的错题/收藏/斩题」页的搜索行为一致）。
    """
    spec = KINDS[kind]
    conditions: List[Any] = [
        spec.model.user_id == user_id,
        *_active_condition(spec, active_only),
    ]
    if bank_id is not None:
        conditions.append(spec.model.bank_id == int(bank_id))
    kw = (keyword or "").strip()
    if kw:
        # 与既有列表接口一致用 LIKE 模糊（不转义通配符）：写操作不受影响，
        # 最坏是多召回几条。刻意不在这里「改良」，否则与页面上的搜索结果不一致。
        conditions.append(QuestionMain.question_text.ilike(f"%{kw}%"))

    joined = (
        select(spec.model, QuestionMain, QuestionBank.bank_name)
        .join(QuestionMain, spec.model.question_id == QuestionMain.id)
        .join(QuestionBank, QuestionMain.bank_id == QuestionBank.id)
        .where(*conditions)
    )

    # 命中总量单独数一次（与「查一页」共用同一套 conditions，口径不会分叉）
    total = int(
        await db.scalar(
            select(func.count())
            .select_from(spec.model)
            .join(QuestionMain, spec.model.question_id == QuestionMain.id)
            .where(*conditions)
        )
        or 0
    )

    rows = (
        await db.execute(
            joined.order_by(spec.order_column.desc(), spec.id_column.desc())
            .offset(max(offset, 0))
            .limit(max(1, limit))
        )
    ).all()
    return [(r[0], r[1], r[2]) for r in rows], total


async def get_record(
    db: AsyncSession, user_id: int, kind: str, record_id: Any
) -> Optional[Any]:
    """按 (记录 id + 自己的 user_id) 定位记录；查不到返回 None。

    ⚠️ **本轮重点验收项**：`user_id` 条件在这里，不在调用方 ——
    调用方只要漏带一次，就是水平越权。所以它写在 SQL 里、且是全模块唯一入口。
    """
    spec = KINDS[kind]
    try:
        rid = int(record_id)
    except (TypeError, ValueError):
        return None
    row = (
        await db.execute(
            select(spec.model).where(
                spec.id_column == rid,
                spec.model.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    return row


async def get_record_by_question(
    db: AsyncSession, user_id: int, kind: str, question_id: Any
) -> Optional[Any]:
    """按「(自己的 user_id, 题目 id)」取这类记录（一题一条）；没有返回 None。

    ⚠️ 与 `add_record` 的「已存在」查找**是同一个条件**，所以 `add_record` 也直接调它
    （一个谓词只能有一处实现 —— 两处各写一份，迟早出现「add 判定已存在、调用方判定不存在」）。
    用途：`add` 的**回退**需要改前快照（`error_count` 之类），而 upsert 之后就读不到旧值了。
    """
    spec = KINDS[kind]
    try:
        qid = int(question_id)
    except (TypeError, ValueError):
        return None
    row = (
        await db.execute(
            select(spec.model).where(
                spec.model.user_id == user_id,
                spec.model.question_id == qid,
            )
        )
    ).scalar_one_or_none()
    return row


async def brief_of(
    db: AsyncSession,
    user_id: int,
    kind: str,
    record: Any,
    question: Optional[QuestionMain] = None,
    bank_name: Optional[str] = None,
) -> Dict[str, Any]:
    """把一条记录 + 它的题目拼成给模型/前端看的 camelCase 字典"""
    spec = KINDS[kind]
    if question is None:
        question = await db.get(QuestionMain, int(record.question_id))
    if bank_name is None:
        bank_name = await db.scalar(
            select(QuestionBank.bank_name).where(QuestionBank.id == record.bank_id)
        )

    text = (question.question_text or "") if question else ""
    data: Dict[str, Any] = {
        spec.id_key: getattr(record, spec.id_column.key),
        "questionId": record.question_id,
        "bankId": record.bank_id,
        "bankName": bank_name,
        "questionType": question.question_type if question else None,
        # 题型文案与 `question_write_service.QUESTION_TYPE_TEXT` 同一份（避免两处枚举漂移）
        "questionTypeText": _question_type_text(question.question_type if question else None),
        "difficulty": question.difficulty if question else None,
        # `preview` 是前端 `TITLE_KEYS` 的一员 —— 列表卡片会拿它当标题
        "preview": text[:80] + ("…" if len(text) > 80 else ""),
        "notes": getattr(record, "notes", None),
        "tags": getattr(record, "tags", None),
        "createTime": _iso(getattr(record, "create_time", None)),
    }
    if kind == KIND_ERROR:
        data.update(
            {
                "errorCount": record.error_count,
                "isMastered": record.is_mastered,
                # ⚠️ 这里**刻意不给** `status`（2026-09-22 删）：唯一会把它送到用户面前的路径是
                #    `question_flag_manage.list`，而那条路径的 WHERE 里已经带了 `status == 1`
                #    （`list_records` 的 `active_only=True`，见 `_active_condition`）——
                #    于是它恒为 1，只会渲染成一行「状态：1」，对用户和模型都是零信息。
                #    「已掌握」这件事由 `isMastered` 表达（前端有「未掌握/已掌握」的枚举）。
                #    ⚠️ 不要再让它回到全局枚举表：`bank_share.status` 的 `'0'`=有效 / `'1'`=已撤销，
                #    与错题 `1`=活跃**语义相反**，一张全局表必然给其中一个显示反。
                "lastErrorTime": _iso(record.last_error_time),
            }
        )
    elif kind == KIND_FAVORITE:
        data.update(
            {
                "favoriteStatus": record.favorite_status,
                "correctTimes": record.correct_times,
                "errorTimes": record.error_times,
                "reviewCount": record.review_count,
                "isStarred": record.is_starred,
            }
        )
    else:
        data.update(
            {
                "markedStatus": record.marked_status,
                "markedType": record.marked_type,
                "markedTypeText": MARKED_TYPE_TEXT.get(record.marked_type, "未知"),
                "difficultyLevel": record.difficulty_level,
                "reviewCount": record.review_count,
                "isMastered": record.is_mastered,
            }
        )
    return data


def _question_type_text(qtype: Optional[int]) -> Optional[str]:
    from app.services.question_write_service import QUESTION_TYPE_TEXT

    if qtype is None:
        return None
    return QUESTION_TYPE_TEXT.get(int(qtype), "未知")


def _iso(value: Any) -> Optional[str]:
    return value.isoformat(sep=" ") if value else None


# ---------------------------------------------------------------- 写入


async def add_record(
    db: AsyncSession,
    user_id: int,
    kind: str,
    question: QuestionMain,
    bank_id: int,
    *,
    notes: Optional[str] = None,
    tags: Optional[str] = None,
    marked_type: Optional[int] = None,
) -> Tuple[Any, bool]:
    """把一道题加进某类记录（已存在则**恢复/累加**，绝不重复插一行）。

    Returns: `(record, created)`；`created=False` 表示复用了已有行。

    三类的「已存在」处理与既有接口一致：
      · 错题：`error_count += 1` + `last_error_time = now` + **重新激活**
        （`status=1, is_mastered=0`，与 `report_practice` 的「已掌握后再做错」同一处理）
      · 收藏：`favorite_status = 1`
      · 斩题：`marked_status = 1`
    """
    spec = KINDS[kind]
    now = datetime.now()

    # 「已存在」的查找收在 `get_record_by_question`（`question_flag_manage` 的
    # undo 也要用同一条谓词去取改前快照）—— 别在这里再写一份
    existing = await get_record_by_question(db, user_id, kind, question.id)

    if existing is not None:
        if kind == KIND_ERROR:
            existing.error_count = (existing.error_count or 0) + 1
            existing.last_error_time = now
            existing.status = 1
            existing.is_mastered = 0
        elif kind == KIND_FAVORITE:
            existing.favorite_status = 1
        else:
            existing.marked_status = 1
        if notes is not None:
            existing.notes = notes
        if tags is not None:
            existing.tags = tags
        if kind == KIND_MARKED and marked_type is not None:
            existing.marked_type = marked_type
        if kind == KIND_MARKED:
            existing.bank_id = int(bank_id)
        await db.flush()
        return existing, False

    record = spec.model(
        user_id=user_id,
        question_id=question.id,
        bank_id=int(bank_id),
        notes=notes,
        tags=tags,
    )
    if kind == KIND_ERROR:
        record.error_count = 1
        record.error_time = now
        record.last_error_time = now
        record.status = 1
        record.is_mastered = 0
    elif kind == KIND_FAVORITE:
        record.favorite_status = 1
    else:
        record.marked_status = 1
        record.marked_type = int(marked_type or 1)
        record.is_mastered = 0
    db.add(record)
    await db.flush()
    return record, True


async def mark_mastered(db: AsyncSession, user_id: int, record: Any) -> bool:
    """把一条错题标记为「已掌握」（`is_mastered=1, status=0`）

    与 `POST /questionError/questionError/markMastered` 完全同口径。
    再答错时 `report_practice` 会把它重新激活 —— 所以这个操作**不算删除**，
    不需要当成破坏性动作。
    """
    if int(record.user_id or 0) != int(user_id or 0):
        return False
    record.is_mastered = 1
    record.status = 0
    await db.flush()
    return True


async def remove_record(
    db: AsyncSession, user_id: int, kind: str, record: Any
) -> bool:
    """物理删掉一条记录（= 前端的「取消收藏 / 取消斩题 / 删除错题」）

    ⚠️ DELETE 语句里**再带一次 `user_id`**：`record` 已经过 `get_record` 归属校验，
    但删数据这一刀不接受「调用方保证」——多一个条件在这里的代价是零。
    """
    spec = KINDS[kind]
    if record is None or int(record.user_id or 0) != int(user_id or 0):
        return False
    result = await db.execute(
        delete(spec.model).where(
            spec.id_column == getattr(record, spec.id_column.key),
            spec.model.user_id == user_id,
        )
    )
    await db.flush()
    return bool(result.rowcount)


async def count_records(db: AsyncSession, user_id: int, kind: str) -> int:
    """某类记录的活跃条数（列表分页之外的「总量」入口）"""
    spec = KINDS[kind]
    return int(
        await db.scalar(
            select(func.count()).where(
                spec.model.user_id == user_id,
                *_active_condition(spec, True),
            )
        )
        or 0
    )


__all__ = [
    "DEFAULT_LIMIT",
    "KIND_ERROR",
    "KIND_FAVORITE",
    "KIND_MARKED",
    "KINDS",
    "MARKED_TYPE_TEXT",
    "MAX_LIMIT",
    "add_record",
    "brief_of",
    "can_view_bank",
    "count_records",
    "get_record",
    "get_record_by_question",
    "kind_spec",
    "list_records",
    "mark_mastered",
    "remove_record",
    "resolve_visible_question",
    "shared_bank_ids",
]
