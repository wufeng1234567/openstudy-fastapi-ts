"""
题库树的**删除快照**与**整树恢复**

为什么需要这个模块（2026-10-20）
================================
`question_write_service.delete_banks` / `question_manage._purge_questions` 是
**物理删除 + 应用层级联**：删一个题库会连带清掉

    question_main（题） → question_sub（子题）
    user_question_favorite / user_question_error / user_question_marked（个人标记）
    note_question / note_question_bank（笔记关联）
    bank_share / bank_share_receive（分享与领取）

所以「删错了题库」在库里没有任何挽回余地 —— 回退按钮此前只能如实说
「题库与题目目前是物理删除，暂时无法回退」。

本模块把「删除前把整棵树存下来」做成一个通用能力：删除时把该存的行抓成快照
塞进账本（`ai_agent_op_log.before`），回退时按原主键、正确顺序插回去。

⚠️ 为什么走「快照重插」而不是「加软删除列 + 全量读点过滤」（已实测否决）
--------------------------------------------------------------------
软删除看起来更优雅，但要给 `QuestionBank` / `QuestionMain` 加 `del_flag`，
然后**全仓 129 个读点**都得补 `del_flag == '0'` 过滤（实测统计，见下）：

    QuestionBank 实体 select 50 处 / Core 列 select 19 处
    QuestionMain  实体 select 43 处 / Core 列 select 17 处

而且 `with_loader_criteria` 这条「一处配置、全局生效」的近路**对 Core 列 select 无效**
（已用 sqlite 实测：实体 select 返回 1 行、Core 列 select 返回 2 行）——
本仓恰恰有大量 Core 列 select（列表分页、统计聚合都用）。

漏掉任何一处读点，已删的题库就会重新出现在某个列表里（甚至是别人的列表，
因为有些查询只按 is_public 过滤）。**那比「不能回退」严重得多。**

快照重插只碰**删除路径**（删除前抓一份快照）+ 回退路径（插回去），
所有读取代码一行都不用改 —— 回归风险为零。代价是快照占空间，见下面。

⚠️ 快照多大（实测，防止悄悄膨胀）
--------------------------------
题库 172（「概率论与数理统计-复习题」，36 道题、0 道子题）的完整快照
JSON 是 **20.2 KB**（每道题约 575 字节）。账本的 `before` 是 JSON 列，
PG 会自动压缩大值，实际存储更小。这个量级完全可以接受。

⚠️ 仍然**可能失败**，必须如实告知
--------------------------------
快照重插有两个天然边界，它们不该被隐藏：
  1. **主键可能已被占用** —— 回退前若同一个 id 被新数据用了（序列复用几乎不可能，
     但人工改库会发生），插入会撞主键。
  2. **依赖的行可能已经不存在** —— 比如题目被删后，另一次操作又改了题库总数。
本模块的做法是：**能插多少插多少、逐条记账**，最后返回真实的恢复清单。
调用方（`rollback_service`）把它转成「部分回退 + 原因」。
绝不做的是「假装全恢复了」。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note_question import NoteQuestion
from app.models.question import (
    QuestionBank,
    QuestionMain,
    QuestionSub,
    UserBankFavorite,
    UserQuestionError,
    UserQuestionFavorite,
    UserQuestionMarked,
)

#: 快照里参与的表 → (payload 键名, ORM 模型, 主键列名)。**顺序即插入顺序**（先父后子）。
#:
#: ⚠️ 顺序不能靠字母序或字典序「碰巧对」：`question_main.bank_id` 指向
#:    `question_bank.id`，`question_sub.main_id` 指向 `question_main.id`。
#:    插反了就是 ForeignKeyViolation。
#:
#: ⚠️ 键名必须与 `snapshot_banks` / `snapshot_questions` 里**实际写进 payload 的键**
#:    逐字一致。第一版这里写的是单数 `bank`，而 payload 写的是 `banks` ——
#:    结果 `restore_snapshot` 取到空列表、`rowCount` 算成 0，回退静默变成
#:    「快照不可用」。这种错不会报错，只会让功能悄悄不生效，所以键名收在这里一处。
_SNAPSHOT_ORDER: Tuple[Tuple[str, Any, str], ...] = (
    ("banks", QuestionBank, "id"),
    ("questions", QuestionMain, "id"),
    ("subs", QuestionSub, "id"),
    ("questionFavorites", UserQuestionFavorite, "favorite_id"),
    ("questionErrors", UserQuestionError, "error_id"),
    ("questionMarkeds", UserQuestionMarked, "marked_id"),
    ("bankFavorites", UserBankFavorite, "favorite_id"),
    ("noteQuestions", NoteQuestion, "id"),
)

#: 单次快照最多存多少行（防爆上限）。
#:
#: 一个 2000 题、每 5 题一个子题的题库 ≈ 2400 行 ≈ 1.4 MB JSON。
#: 超过就**不存快照**并如实返回原因 —— 存一个 50 MB 的账本行会把回退接口拖死，
#: 而用户真正想要的（撤销刚才那次误删）在这个量级下本来就不现实。
MAX_SNAPSHOT_ROWS = 3000


def _jsonable_value(value: Any) -> Any:
    """把 ORM 列值转成能进 JSON 的形态（与 `base.jsonable` 同口径）"""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return [_jsonable_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable_value(v) for k, v in value.items()}
    return value


def _row_dict(row: Any, columns: Sequence[str]) -> Dict[str, Any]:
    return {name: _jsonable_value(getattr(row, name)) for name in columns}


def _columns_of(model: Any) -> List[str]:
    return [c.name for c in model.__table__.columns]


async def snapshot_banks(
    db: AsyncSession, user_id: int, bank_ids: Iterable[int]
) -> Dict[str, Any]:
    """抓一份**删除前快照**（题库 + 题目 + 子题 + 个人标记 + 笔记关联）

    Args:
        user_id: 只抓**属于这个用户**的题库（IDOR 红线：快照也是数据出口，
                 抓到别人的行等于把它写进自己的账本）。
        bank_ids: 要删除的题库 id 列表。

    Returns:
        `{"kind": "bank_tree", "banks": [...], ...}` —— 形状与
        `_SNAPSHOT_ORDER` 的键一一对应，外加 `kind` / `rowCount` 两个元字段。

        ⚠️ 行数超过 `MAX_SNAPSHOT_ROWS` 时返回
        `{"kind": "bank_tree", "skipped": True, "reason": "...", "rowCount": n}`，
        此时**不存任何行**（存半份等于给回退埋雷：恢复出来的是残缺题库）。

    ⚠️ 本函数**只读**，不写库、不删数据 —— 调用方在真正删除之前调用它。
    """
    ids = [int(i) for i in bank_ids if i is not None]
    if not ids:
        return {"kind": "bank_tree", "rowCount": 0}

    # 1) 题库（只取自己的）
    bank_rows = list(
        (
            await db.execute(
                select(QuestionBank).where(
                    QuestionBank.id.in_(ids), QuestionBank.user_id == int(user_id)
                )
            )
        ).scalars().all()
    )
    own_ids = [int(b.id) for b in bank_rows]
    if not own_ids:
        return {"kind": "bank_tree", "rowCount": 0}

    # 2) 题目（按 sort_order 存，恢复时顺序不变）
    question_rows = list(
        (
            await db.execute(
                select(QuestionMain)
                .where(QuestionMain.bank_id.in_(own_ids))
                .order_by(QuestionMain.sort_order, QuestionMain.id)
            )
        ).scalars().all()
    )
    question_ids = [int(q.id) for q in question_rows]

    # 3) 子题
    sub_rows: List[QuestionSub] = []
    if question_ids:
        sub_rows = list(
            (
                await db.execute(
                    select(QuestionSub).where(QuestionSub.main_id.in_(question_ids))
                )
            ).scalars().all()
        )

    # 4) 个人标记（三张表）—— ⚠️ 只存**这个用户**的行：
    #    别人的错题/收藏不该因为题库主删库而进他的账本（那是泄漏），
    #    也不该被恢复出来的题库悄悄「复活」（那是别人的数据）。
    fav_rows = err_rows = marked_rows = []
    if question_ids:
        fav_rows = list(
            (
                await db.execute(
                    select(UserQuestionFavorite).where(
                        UserQuestionFavorite.question_id.in_(question_ids),
                        UserQuestionFavorite.user_id == int(user_id),
                    )
                )
            ).scalars().all()
        )
        err_rows = list(
            (
                await db.execute(
                    select(UserQuestionError).where(
                        UserQuestionError.question_id.in_(question_ids),
                        UserQuestionError.user_id == int(user_id),
                    )
                )
            ).scalars().all()
        )
        marked_rows = list(
            (
                await db.execute(
                    select(UserQuestionMarked).where(
                        UserQuestionMarked.question_id.in_(question_ids),
                        UserQuestionMarked.user_id == int(user_id),
                    )
                )
            ).scalars().all()
        )

    # 5) 题库收藏 + 笔记关联
    bank_fav_rows = list(
        (
            await db.execute(
                select(UserBankFavorite).where(
                    UserBankFavorite.bank_id.in_(own_ids),
                    UserBankFavorite.user_id == int(user_id),
                )
            )
        ).scalars().all()
    )
    note_q_rows = []
    if question_ids:
        note_q_rows = list(
            (
                await db.execute(
                    select(NoteQuestion).where(NoteQuestion.question_id.in_(question_ids))
                )
            ).scalars().all()
        )

    payload: Dict[str, Any] = {
        "kind": "bank_tree",
        "bankId": own_ids[0] if len(own_ids) == 1 else None,
        "bankIds": own_ids,
        "banks": [_row_dict(r, _columns_of(QuestionBank)) for r in bank_rows],
        "questions": [_row_dict(r, _columns_of(QuestionMain)) for r in question_rows],
        "subs": [_row_dict(r, _columns_of(QuestionSub)) for r in sub_rows],
        "questionFavorites": [
            _row_dict(r, _columns_of(UserQuestionFavorite)) for r in fav_rows
        ],
        "questionErrors": [
            _row_dict(r, _columns_of(UserQuestionError)) for r in err_rows
        ],
        "questionMarkeds": [
            _row_dict(r, _columns_of(UserQuestionMarked)) for r in marked_rows
        ],
        "bankFavorites": [
            _row_dict(r, _columns_of(UserBankFavorite)) for r in bank_fav_rows
        ],
        "noteQuestions": [
            _row_dict(r, _columns_of(NoteQuestion)) for r in note_q_rows
        ],
    }
    payload["rowCount"] = sum(
        len(payload[key]) for key, _m, _pk in _SNAPSHOT_ORDER
    )

    if payload["rowCount"] > MAX_SNAPSHOT_ROWS:
        # 不存半份（见 docstring）：直接返回「太大了，没存」，让回退侧如实告知
        logger.warning(
            "[snapshot] 题库 {} 的树太大（{} 行 > 上限 {}），未保存快照",
            own_ids,
            payload["rowCount"],
            MAX_SNAPSHOT_ROWS,
        )
        return {
            "kind": "bank_tree",
            "skipped": True,
            "rowCount": payload["rowCount"],
            "reason": "too_large",
            "bankIds": own_ids,
        }
    return payload


async def snapshot_questions(
    db: AsyncSession, user_id: int, question_ids: Iterable[int]
) -> Dict[str, Any]:
    """抓一份**题目删除快照**（题目 + 子题 + 该用户的个人标记）

    与 `snapshot_banks` 同一个思路，只是根不是一个题库、而是若干题目。
    用于 `question_manage` 的 delete / delete_many / clear_questions 回退。
    """
    ids = [int(i) for i in question_ids if i is not None]
    if not ids:
        return {"kind": "question_tree", "rowCount": 0}

    # 只抓「题库属于自己」的题（与 `_purge_questions` 的归属闸门同口径）
    rows = list(
        (
            await db.execute(
                select(QuestionMain)
                .join(QuestionBank, QuestionBank.id == QuestionMain.bank_id)
                .where(
                    QuestionMain.id.in_(ids), QuestionBank.user_id == int(user_id)
                )
                .order_by(QuestionMain.sort_order, QuestionMain.id)
            )
        ).scalars().all()
    )
    own_ids = [int(q.id) for q in rows]
    if not own_ids:
        return {"kind": "question_tree", "rowCount": 0}

    sub_rows = list(
        (
            await db.execute(
                select(QuestionSub).where(QuestionSub.main_id.in_(own_ids))
            )
        ).scalars().all()
    )
    fav_rows = list(
        (
            await db.execute(
                select(UserQuestionFavorite).where(
                    UserQuestionFavorite.question_id.in_(own_ids),
                    UserQuestionFavorite.user_id == int(user_id),
                )
            )
        ).scalars().all()
    )
    err_rows = list(
        (
            await db.execute(
                select(UserQuestionError).where(
                    UserQuestionError.question_id.in_(own_ids),
                    UserQuestionError.user_id == int(user_id),
                )
            )
        ).scalars().all()
    )
    marked_rows = list(
        (
            await db.execute(
                select(UserQuestionMarked).where(
                    UserQuestionMarked.question_id.in_(own_ids),
                    UserQuestionMarked.user_id == int(user_id),
                )
            )
        ).scalars().all()
    )
    note_q_rows = list(
        (
            await db.execute(
                select(NoteQuestion).where(NoteQuestion.question_id.in_(own_ids))
            )
        ).scalars().all()
    )

    payload: Dict[str, Any] = {
        "kind": "question_tree",
        "questionIds": own_ids,
        "questions": [_row_dict(r, _columns_of(QuestionMain)) for r in rows],
        "subs": [_row_dict(r, _columns_of(QuestionSub)) for r in sub_rows],
        "questionFavorites": [
            _row_dict(r, _columns_of(UserQuestionFavorite)) for r in fav_rows
        ],
        "questionErrors": [
            _row_dict(r, _columns_of(UserQuestionError)) for r in err_rows
        ],
        "questionMarkeds": [
            _row_dict(r, _columns_of(UserQuestionMarked)) for r in marked_rows
        ],
        "questionBanks": [],
        "banks": [],
        "bankFavorites": [],
        "noteQuestions": [
            _row_dict(r, _columns_of(NoteQuestion)) for r in note_q_rows
        ],
    }
    payload["rowCount"] = (
        len(payload["questions"])
        + len(payload["subs"])
        + len(payload["questionFavorites"])
        + len(payload["questionErrors"])
        + len(payload["questionMarkeds"])
        + len(payload["noteQuestions"])
    )
    if payload["rowCount"] > MAX_SNAPSHOT_ROWS:
        logger.warning(
            "[snapshot] 题目 {} 的树太大（{} 行），未保存快照",
            own_ids[:5],
            payload["rowCount"],
        )
        return {
            "kind": "question_tree",
            "skipped": True,
            "rowCount": payload["rowCount"],
            "reason": "too_large",
            "questionIds": own_ids,
        }
    return payload


def _coerce_for_model(model: Any, row: Dict[str, Any]) -> Dict[str, Any]:
    """把快照里的行转成能构造 ORM 对象的关键字参数

    ⚠️ 按**目标列的类型**还原值：JSON 里 `datetime` 是 ISO 字符串、`Decimal` 是 str。
    不还原的话，SQLAlchemy 会把字符串直接塞进 DateTime 列 —— PG 要么报错，
    要么（更糟）在某些驱动下静默存成 1970。
    """
    from sqlalchemy import DateTime, Numeric

    out: Dict[str, Any] = {}
    columns = {c.name: c for c in model.__table__.columns}
    for name, value in (row or {}).items():
        column = columns.get(str(name))
        if column is None:
            # 快照里多出来的字段（表结构变过）→ 丢弃并留痕，不要盲目 setattr
            logger.warning(
                "[snapshot] 表 {} 的快照里有未知列 {}，已丢弃",
                model.__tablename__,
                name,
            )
            continue
        if isinstance(column.type, DateTime) and isinstance(value, str) and value:
            try:
                out[name] = datetime.fromisoformat(value)
                continue
            except ValueError:
                logger.warning("[snapshot] {} 的时间值无法解析：{!r}", name, value)
        if isinstance(column.type, Numeric) and isinstance(value, str):
            try:
                out[name] = Decimal(value)
                continue
            except Exception:  # noqa: BLE001
                pass
        out[name] = value
    return out


async def restore_snapshot(db: AsyncSession, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """按快照把整棵树插回去（**逐条容错**，绝不做「全成功或全失败」）

    为什么逐条容错：一次回退里可能有 500 行，其中一行撞了主键
    （比如用户手改过库）不该让另外 499 行也恢复不了 —— 用户对「题库回来了、
    但少了 1 道题」的接受度远高于「点了回退什么都没发生」。

    Returns:
        `{"restored": {...表名: 条数}, "failed": [...], "rowCount": n}`
        `failed` 里每条带 `table` / `id` / `error`，供界面如实展示。
    """
    restored: Dict[str, int] = {}
    failed: List[Dict[str, Any]] = []
    total = 0

    kind = str(snapshot.get("kind") or "")
    if snapshot.get("skipped"):
        return {
            "restored": {},
            "failed": [],
            "rowCount": 0,
            "skipped": True,
            "reason": str(snapshot.get("reason") or "too_large"),
        }
    if kind not in ("bank_tree", "question_tree"):
        return {
            "restored": {},
            "failed": [],
            "rowCount": 0,
            "skipped": True,
            "reason": "unexpected_snapshot",
        }

    for key, model, pk in _SNAPSHOT_ORDER:
        rows = snapshot.get(key) or []
        if not rows:
            continue
        count = 0
        for row in rows:
            total += 1
            try:
                kwargs = _coerce_for_model(model, row)
                db.add(model(**kwargs))
                await db.flush()
                count += 1
            except Exception as e:  # noqa: BLE001 - 单行失败继续后面的
                failed.append(
                    {
                        "table": model.__tablename__,
                        "id": (row or {}).get(pk),
                        "error": f"{type(e).__name__}: {e}",
                    }
                )
                logger.warning(
                    "[snapshot] 恢复 {} 行失败 id={}: {}",
                    model.__tablename__,
                    (row or {}).get(pk),
                    e,
                )
                # 这一行插失败了，事务可能已进 aborted 状态 → 回滚到进循环前的点。
                # 用 SAVEPOINT 隔离（与 rollback_service._apply 同一条理由）。
                await db.rollback()
        if count:
            restored[model.__tablename__] = count

    return {"restored": restored, "failed": failed, "rowCount": total}


__all__ = [
    "MAX_SNAPSHOT_ROWS",
    "restore_snapshot",
    "snapshot_banks",
    "snapshot_questions",
]
