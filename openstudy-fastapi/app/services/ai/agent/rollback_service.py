"""
「一轮操作的回退」—— 账本写入（record_op）+ 逆操作执行（rollback_turn）

用户口径（原话）：
> 「每轮聊天结束的末尾添加一个回退组件 用户点击后 自动回退 撤销本次的所有操作
>  就像 coding agent 那样的」

三个角色（别混，见 `base.py` 的 undo 契约段）
--------------------------------------------
  · **工具**声明怎么撤（`AgentTool.undo_plan`）+ 把改前状态塞进信封的 `UNDO_BEFORE_KEY`；
  · **本模块的 `record_op`** 在唯一的工具收口（`loop._execute_tool`）里把每次成功的写操作
    记进账本 `ai_agent_op_log`（**与数据同一个会话**，一起提交 / 一起回滚）；
  · **本模块的 `rollback_turn`** 读账本、**倒序**执行逆操作。

⚠️ 为什么「一轮 = N 个独立事务」，回退只能靠逆操作
--------------------------------------------------
`loop.py:1122` 每完成一次写工具就 `commit()` 一次（流式响应下不能依赖 `get_db` 的
teardown），所以一轮里的若干次写入**不是**一个事务 —— 想撤只能做逆操作，
不能靠 `ROLLBACK`。（ds-free 单步执行靠 teardown 提交，同样是一次一个事务。）

⚠️ `op_index` 用 `MAX+1`，不用「行数 +1」
-----------------------------------------
行数会被任何删除 / 回填打乱；`MAX` 只增。并发同 turn 的两次请求理论上可能拿到同一个值，
所以回退排序是 `op_index DESC, id DESC`（`id` 兜底，顺序仍然确定）。

⚠️ 幂等 + 一次失败不拖垮整轮
----------------------------
  · `undone_at` 非空的行**直接跳过、不执行** → 第二次点击 `reverted=0`、一行数据都不动；
  · `undoable=False` 的行进 `skipped`（带原因），**绝不执行**；
  · 单条逆操作失败进 `failed` 且**继续后面的**（用 SAVEPOINT 隔离 —— 见 `rollback_turn`）。

⚠️ 归属：只按 `user_id` 过滤，**不接受外部传进来的 userId**
----------------------------------------------------------
（本仓 IDOR 红线：`core/security.resolve_user_scope`；账本行与目标行的 WHERE 里
都带 user_id，且 `uid<=0` / `turn_id` 为空时**直接返回空结果** —— 空 turn_id 当通配符
会把整个会话的行扫进来，那是灾难性的越权回退。）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger
from sqlalchemy import DateTime, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_memory import AiAgentMemory
from app.models.agent_op_log import AiAgentOpLog
from app.models.agent_config import AiAgentConfig
from app.models.bank_share import BankShare, BankShareReceive
from app.models.note import Note
from app.models.question import (
    UserQuestionError,
    UserQuestionFavorite,
    UserQuestionMarked,
)
from app.models.rag import RagKnowledgeBase
from app.services.ai import memory_service
from app.services.ai.agent.base import (
    OP_DELETE_RECORD,
    OP_INSERT_RECORD,
    OP_RESTORE,
    OP_RESTORE_FIELDS,
    OP_RESTORE_MEMORY,
    OP_RESTORE_TREE,
    OP_SOFT_DELETE,
    REASON_AFFECTS_OTHERS,
    REASON_CONTENT_DESTROYED,
    REASON_DOCUMENTS_DESTROYED,
    REASON_MISSING_SOFT_DELETE,
    REASON_MISSING_TARGET_ID,
    REASON_NOT_DECLARED,
    REASON_NOT_IN_V1,
    REASON_NO_BEFORE_STATE,
    jsonable,
)

# ---------------------------------------------------------------------------
# 原因码 → 给用户看的中文
# ---------------------------------------------------------------------------
# ⚠️ 账本里存的是**原因码**（机器可读、稳定、能当判据），界面要显示的是**中文**。
#    两者刻意分开：把中文写进库，改一次文案就要数据迁移；把码直接给用户看，
#    界面就会出现一行英文（`missing_soft_delete`）—— 本仓已经踩过「英文机器码
#    糊在用户脸上」好几次（见 `question_mark_manage` 的 `resultStatusText`）。
#    所以这个映射表就是那层翻译，**由回退结果里同时下发 reason + reasonText**。
REASON_TEXT: Dict[str, str] = {
    REASON_NOT_DECLARED: "这个操作还没有回退实现",
    REASON_MISSING_SOFT_DELETE: "删除时的数据快照不可用，无法回退",
    REASON_CONTENT_DESTROYED: "文档正文与分块已被物理删除（重建要重算向量），无法回退",
    REASON_AFFECTS_OTHERS: "这条操作影响到了其他用户（通知已发出），无法完全回退",
    REASON_NO_BEFORE_STATE: "没有记录修改前的值，无法回退",
    REASON_MISSING_TARGET_ID: "回执里没有可定位的数据行 ID，无法回退",
    REASON_NOT_IN_V1: "这一类操作本轮暂不支持回退",
    REASON_DOCUMENTS_DESTROYED: "知识库已恢复，但其中的文档与分块已被物理删除，无法恢复",
    # ---- 2026-10-20 新增（题库/题目整树恢复的两条边界）----
    #: 整树重插时部分行失败（撞主键 / 快照缺行）→ 界面上标「部分回退」
    "partial_restored": "大部分内容已恢复，但有个别行没能插回来（详见失败清单）",
    #: 删除时题库太大、快照未保存（见 `bank_tree_snapshot.MAX_SNAPSHOT_ROWS`）
    "too_large": "题库太大，删除时没有保存数据快照，无法回退",
}

# ---------------------------------------------------------------------------
# 没声明 undo 的工具 → 原因码（放到这里，不是放到工具里）
# ---------------------------------------------------------------------------
# ⚠️ 2026-10-20 起这张表**清空**：bank_manage / question_manage / bank_share_manage
#    三个工具都已经在各自 `undo_plan` 里声明了逆操作（前两个走整树快照重插、
#    后者走 status 翻转），不再需要「工具级默认原因」。
#    保留下面的空结构与查询函数，是因为将来新加工具时仍需要一条统一的兜底路径
#    —— 但**新工具应当优先在 `undo_plan` 里声明**，而不是往这里塞一行。
_TOOL_REASON_DEFAULTS: Dict[str, str] = {}
# ⚠️ 只写「这一类操作本就不该回退」的原因。已经在 `undo_plan` 里声明过的
#    （note / memory / knowledge_base / question_flag / agent_manage / bank_share /
#    bank_manage / question_manage）**不许**在这里再写一份 —— 两处声明必然漂移。

#: 工具 + action → 原因码（比工具级默认更具体时用），键是 `(tool, action)`
_TOOL_ACTION_REASONS: Dict[tuple, str] = {
    # 2026-10-20：`("bank_share_manage", "revoke") → REASON_AFFECTS_OTHERS` 已删除。
    # 那一项原本表达「撤销分享不可回退」；现在 `bank_share_manage.undo_plan` 能真的把
    # `status` 翻回来，并在 plan 里带 `reason=REASON_AFFECTS_OTHERS`（部分回退语义）。
    # ⚠️ 两处都写就是两个事实来源，必然漂移（见下面那条注释）。
}
# ⚠️ 只写「本轮改不动的工具」的原因。已经在 `undo_plan` 里声明过的（note / memory /
#    knowledge_base / question_flag / agent_manage / bank_share / bank_manage /
#    question_manage）**不许**在这里再写一份 —— 两处声明必然漂移。


# ---------------------------------------------------------------------------
# 目标表登记表（白名单）
# ---------------------------------------------------------------------------
class _Target:
    """一张可被回退的表：ORM 模型 + 主键列名 + 逻辑删列名。

    ⚠️ `restorable()` 只让**真实存在的列**通过：账本里的键名是 JSON 数据，
    绝不能拼进 SQL 文本 —— 这里按 ORM 元数据校验，未知键**丢弃并告警**。

    ⚠️ **归属列可以不是 `user_id`**（2026-10-20 扩展）：`bank_share` / `bank_share_receive`
    的归属列叫 `owner_id`。硬要求 `user_id` 会让这两张表永远进不了白名单 ——
    而它们恰恰是「天然可回退」的表（撤销分享只是把 status 从 '1' 翻回 '0'）。
    用 `user_col` 指定，回退时照旧按它过滤（IDOR 红线不变：只动自己的行）。
    """

    #: 绝不写回的列：主键（行身份）、归属（必须由服务端认定）、创建时间（历史事实）
    _PROTECTED = {"user_id", "owner_id", "create_time"}

    def __init__(
        self,
        model: Any,
        pk: str,
        soft_delete: Optional[str] = None,
        *,
        user_col: str = "user_id",
        alive_value: str = "0",
        deleted_value: str = "2",
    ) -> None:
        self.model = model
        self.pk = pk
        self.soft_delete = soft_delete
        self.columns = {c.name for c in model.__table__.columns}
        self.pk_col = getattr(model, pk)
        self.user_col = getattr(model, user_col)
        #: 「未删」与「已删」的取值。默认是 `del_flag` 的 '0'/'2'；
        #: `bank_share.status` 用 '0'/'1'（'0' 有效 / '1' 已撤销，见 `models/bank_share.py`）。
        #: ⚠️ 不能把这两组值揉成一套：两者语义不同（"逻辑删除" vs "业务状态"），
        #: 混用会让某天给 bank_share 加 del_flag 时一改就错一片。
        self.alive_value = alive_value
        self.deleted_value = deleted_value

    def restorable(self, before: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """把 `before` 过滤成「能写回的列 → 值」（按列类型把 ISO 字符串解析回 datetime）"""
        out: Dict[str, Any] = {}
        dropped: List[str] = []
        for key, value in (before or {}).items():
            name = str(key)
            if name in self.columns and name != self.pk and name not in self._PROTECTED:
                out[name] = self._coerce(name, value)
            else:
                dropped.append(name)
        if dropped:
            # 不静默：账本里多写了字段（或字段被改名）时，这里必须留下线索
            logger.warning(
                "[rollback] 表 {} 的 before 里有不可写回的字段，已丢弃：{}",
                self.model.__tablename__,
                dropped,
            )
        return out

    def _coerce(self, name: str, value: Any) -> Any:
        """按**目标列的类型**还原值（JSON 里 datetime 是 ISO 字符串）"""
        column = self.model.__table__.columns[name]
        if isinstance(column.type, DateTime) and isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:  # pragma: no cover - 账本脏数据
                logger.warning("[rollback] {} 的时间值无法解析：{!r}", name, value)
                return value
        return value


#: 可回退的表（**白名单**：不在表里的 target_table 一律判失败，不做任何 SQL）
_TABLES: Dict[str, _Target] = {
    "note": _Target(Note, "note_id", soft_delete="del_flag"),
    "rag_knowledge_base": _Target(RagKnowledgeBase, "id", soft_delete="del_flag"),
    "ai_agent_memory": _Target(AiAgentMemory, "id", soft_delete="del_flag"),
    "user_question_error": _Target(UserQuestionError, "error_id"),
    "user_question_favorite": _Target(UserQuestionFavorite, "favorite_id"),
    "user_question_marked": _Target(UserQuestionMarked, "marked_id"),
    # ---- 2026-10-20 新增：把「题库 / 分享 / 智能体」三个域接进回退 ----
    #: 用户自定义智能体：本来就有 `del_flag`（见 `models/agent_config.py`），
    #: 只是一直没声明 undo —— 补上即可，无需改表。
    "ai_agent_config": _Target(AiAgentConfig, "id", soft_delete="del_flag"),
    #: 题库分享：没有 `del_flag`，但 `status` 的语义正好是「'0' 有效 / '1' 已撤销」。
    #: ⚠️ 归属列是 `owner_id` 而不是 `user_id` —— 见 `_Target` 的说明。
    "bank_share": _Target(
        BankShare, "id", soft_delete="status", user_col="owner_id",
        alive_value="0", deleted_value="1",
    ),
    #: 分享**领取**记录：`receive` 会新增，撤销分享会把它置失效。同样用 status 翻回。
    "bank_share_receive": _Target(
        BankShareReceive, "id", soft_delete="status", user_col="receiver_id",
        alive_value="0", deleted_value="1",
    ),
}


# ---------------------------------------------------------------------------
# 写入侧：_execute_tool 的收口调用
# ---------------------------------------------------------------------------
def _ints(value: Any) -> List[int]:
    """把「账本里可能脏的 id 列表」解析成 int 列表（**绝不抛**）。

    ⚠️ 账本的 id 来自工具声明的 plan / 信封里的 before，都属于「别人给的数据」。
    直接 `int(...)` 会在 `record_op` 里抛出去 —— 而 `_execute_tool` 外层没有 try，
    那会顺着流式生成器一路炸掉**整个这一轮对话**。记不上账是小事，炸掉用户这一轮是大事。
    """
    out: List[int] = []
    if not isinstance(value, (list, tuple, set, str)):
        return out
    items = value.split(",") if isinstance(value, str) else list(value)
    for item in items:
        try:
            out.append(int(str(item).strip()))
        except (TypeError, ValueError):
            continue
    return out


def _before_ids(before: Any) -> List[int]:
    """从 `before` 里取「目标行 id 列表」（**只**用于 id 不能进回执的场景）。

    目前只有一个：memory `clear` —— 它删多少行要**执行前**才查得出来，而那个 id 列表
    给模型看没有任何意义（回执里只有「已清空 N 条」）。见 `_target_ids_of`。
    """
    if isinstance(before, dict):
        for key in ("memoryIds", "targetIds"):
            ids = _ints(before.get(key))
            if ids:
                return ids
    return []


def _reason_for(tool_name: str, action: str, plan: Optional[Dict[str, Any]]) -> str:
    """这条操作「为什么不能撤」：工具自己声明的优先，其次查工具级/动作级默认表"""
    if plan:
        declared = str(plan.get("reason") or "")
        if declared:
            return declared
    specific = _TOOL_ACTION_REASONS.get((tool_name, action))
    if specific:
        return specific
    return _TOOL_REASON_DEFAULTS.get(tool_name, REASON_NOT_DECLARED)


async def record_op(
    db: AsyncSession,
    *,
    tool: Any,
    params: Dict[str, Any],
    result: Dict[str, Any],
    ctx: Any,
    before: Optional[Dict[str, Any]] = None,
) -> None:
    """把一个**成功的写操作**记进账本（`ai_agent_op_log`）。

    只在 `loop._execute_tool` 里调用 —— 那是两条链路（api 主循环 / ds-free 单步执行）
    唯一的工具收口，挂一处两边都覆盖（与 `memory_hook` 同一位置、同一理由）。

    门槛与 `memory_hook.should_remember` 逐条对齐（**故意各写一份**：那边是「要不要记进
    长期记忆」的策略，将来可能收窄；账本要的是「是不是一次写操作」这个事实，
    收窄记忆策略不该让账本跟着漏行）：
      · `tool.write_operation` 为真；
      · 这个 action 需要确认（工具用自己那份 `_WRITE_ACTIONS` 判定，list/detail 不算）；
      · 回执 `success` 不为 False（失败的操作没写库，不该进账本）。

    ⚠️ **绝不抛异常**（与 memory_hook 同口径）：记账失败不能让用户这一次操作失败。
    但也不能**静默**丢账 —— 丢一行就是「回退按钮漏一次操作」，所以失败必打 warning。
    包一层 SAVEPOINT：即使插入失败（例如历史库还没建这张表），也不会把外层事务
    拖进 aborted 状态（之后所有 SQL 都会报 "current transaction is aborted"）。
    """
    if not getattr(tool, "write_operation", False):
        return
    if not isinstance(result, dict) or result.get("success") is False:
        return
    try:
        if not tool.needs_confirmation(params or {}):
            return
    except Exception:  # noqa: BLE001 - 工具实现异常 → 当成「不需要确认」，不记账
        return

    extra = getattr(ctx, "extra", None) or {}
    turn_id = str(extra.get("turn_id") or "").strip()
    if not turn_id:
        # 没有轮次标识就**不记**（宁缺勿错）：写一行 `turn_id=''` 会与所有「无轮次」的行
        # 混在一起，而回退是按 (session, turn) 取的 —— 那等于给回退埋一条「一撤撤一片」的路
        logger.warning(
            "[rollback] 缺少 turn_id，跳过记账 tool={} action={}",
            getattr(tool, "name", ""),
            (params or {}).get("action"),
        )
        return

    action = str((params or {}).get("action") or "")
    try:
        # ⚠️ `before` 必须传给 `undo_plan`：`_execute_tool` 已经把它从 `result` 里
        #    pop 掉了，所以工具无法再从 result 读到自己的快照（见 base 的签名说明）。
        #    题库/题目删除的整树快照正是靠这条路才能被声明。
        #
        # ⚠️ 这里**不再**用 `except TypeError` 兜「旧签名」了（2026-10-20 收口）：
        #    那个兜底会把下面这类**真 bug** 误判成"签名不兼容"然后悄悄再试一次 ——
        #    最坏情况是 `undo_plan` 内部的 `TypeError` 被吞掉、操作被记成「没声明」，
        #    用户点回退时看到「这个操作还没有回退实现」，而真正的原因永远查不到。
        #    现在十个工具（含 bank_export 那个恒返回 None 的）签名已统一为
        #    `(params, result, before=None)`，所以不需要兜底了。
        #    新增工具时**必须**照这个签名写，否则记账阶段会抛 TypeError → 记成 not_declared。
        plan = tool.undo_plan(params or {}, result, before)
    except Exception as e:  # noqa: BLE001 - 工具声明坏了 → 当作没声明（但要留痕）
        logger.warning("[rollback] undo_plan 异常 tool={}: {}", getattr(tool, "name", ""), e)
        plan = None
    if plan is not None and not isinstance(plan, dict):
        logger.warning("[rollback] undo_plan 返回值不是 dict，已忽略 tool={}", getattr(tool, "name", ""))
        plan = None

    plan = dict(plan or {})
    # `before` 由 `_execute_tool` 从信封里摘出来（见 base.UNDO_BEFORE_KEY）；
    # 工具也可以在 plan 里直接给（两条路都支持，plan 里的优先）
    if before is not None and not plan.get("before"):
        plan["before"] = before
    # JSON 列：`datetime` / `Decimal` 在这里**统一**转成可序列化形态（见 base.jsonable）。
    # 放在这一处而不是让每个工具自己转 —— 少一个工具忘了转，就是「写操作被判失败」。
    stored_before = jsonable(plan.get("before")) if plan.get("before") else None

    op = str(plan.get("op") or "")
    undoable = bool(plan.get("undoable", bool(op))) and bool(op)
    target_ids = _ints(plan.get("targetIds"))
    reason = "" if undoable and not plan.get("reason") else _reason_for(
        getattr(tool, "name", ""), action, plan if plan else None
    )
    # ⚠️ `undoable=True` 且 reason 非空 = **部分回退**（如知识库：库能回来、文档分块不能）
    if undoable and not plan.get("reason") and not (target_ids or _before_ids(stored_before)):
        # 说得出「怎么撤」却定位不到行 —— 那是缺陷，不许静默变成「点了没反应」
        undoable = False
        reason = REASON_MISSING_TARGET_ID

    uid = int(getattr(ctx, "user_id", 0) or 0)
    session_id = str(getattr(ctx, "session_id", None) or "")
    now = datetime.now()
    try:
        async with db.begin_nested():
            next_index = int(
                await db.scalar(
                    select(func.coalesce(func.max(AiAgentOpLog.op_index), 0)).where(
                        AiAgentOpLog.user_id == uid,
                        AiAgentOpLog.session_id == session_id,
                        AiAgentOpLog.turn_id == turn_id,
                    )
                )
                or 0
            ) + 1
            db.add(
                AiAgentOpLog(
                    user_id=uid,
                    session_id=session_id,
                    turn_id=turn_id,
                    op_index=next_index,
                    tool=str(getattr(tool, "name", "") or ""),
                    action=action,
                    op=op if undoable else "",
                    target_table=str(plan.get("targetTable") or ""),
                    target_ids=target_ids or None,
                    before=stored_before,
                    undoable=undoable,
                    reason=reason,
                    create_time=now,
                )
            )
            await db.flush()
    except Exception as e:  # noqa: BLE001 - 记账是增强项，失败只告警（见 docstring）
        logger.warning(
            "[rollback] 记账失败（已忽略，不影响本次操作）tool={} action={} turn={}: {}",
            getattr(tool, "name", ""),
            action,
            turn_id,
            e,
        )


# ---------------------------------------------------------------------------
# 执行侧：回退一轮
# ---------------------------------------------------------------------------
def _target_ids_of(row: AiAgentOpLog) -> List[int]:
    """账本行要动的 id 列表。

    ⚠️ 两条来源：`target_ids`（工具从回执里取的，回执本来就给模型看）与
    `before` 里的 `*Ids`（**只**用于「id 不能进回执」的场景 —— 目前只有一个：
    memory `clear` 在执行前才查出「将被删的 id 列表」，那个列表给模型看没有意义）。
    """
    return _ints(row.target_ids) or _before_ids(row.before)


def _skip_item(row: AiAgentOpLog) -> Dict[str, Any]:
    reason = row.reason or REASON_NOT_DECLARED
    return {
        "tool": row.tool,
        "action": row.action,
        "reason": reason,
        # 中文文案一并给出（界面直接显示；见 REASON_TEXT 的说明）
        "reasonText": REASON_TEXT.get(reason, reason),
    }


async def _apply(db: AsyncSession, uid: int, row: AiAgentOpLog) -> None:
    """执行一条逆操作；失败**抛异常**（由调用方分类到 `failed`）。"""
    # ⚠️ `restore_tree` 走**快照**，不按 `targetTable` 单表操作 —— 它要一次插回
    #    题库 + 题目 + 子题 + 个人标记等一整组表。所以这个分支必须排在
    #    「查 `_TABLES` 白名单」之**前**：否则会被判成「未知的目标表」
    #    （e2e 实测：`ValueError: 未知的目标表（不在可回退白名单里）：'question_bank'`）。
    if row.op == OP_RESTORE_TREE:
        await _apply_restore_tree(db, row)
        return

    target = _TABLES.get(row.target_table or "")
    if target is None:
        raise ValueError(f"未知的目标表（不在可回退白名单里）：{row.target_table!r}")
    ids = _target_ids_of(row)
    if not ids:
        raise ValueError("账本行里没有目标 id")

    if row.op in (OP_RESTORE, OP_SOFT_DELETE):
        if not target.soft_delete:
            raise ValueError(f"表 {row.target_table} 没有逻辑删列，不支持 {row.op}")
        # ⚠️ 取值来自 `_Target`，不是写死的 "0" / "2"：`bank_share.status` 用 '0'/'1'。
        #    写死会让「撤销分享」的回退把 status 写成 '2' —— 那既不是有效也不是已撤销，
        #    而所有查询都按 '0'/'1' 判，等于把这条分享变成谁都看不见的幽灵行。
        value = (
            target.alive_value if row.op == OP_RESTORE else target.deleted_value
        )
        result = await db.execute(
            update(target.model)
            .where(target.pk_col.in_(ids), target.user_col == uid)
            .values({target.soft_delete: value})
        )
        if not (result.rowcount or 0):
            raise RuntimeError(f"没有命中任何行（id={ids}，可能已被改动）")
        return

    if row.op == OP_RESTORE_FIELDS:
        values = target.restorable(row.before)
        if not values:
            raise ValueError("账本里没有可写回的字段（before 为空）")
        result = await db.execute(
            update(target.model)
            .where(target.pk_col == ids[0], target.user_col == uid)
            .values(values)
        )
        if not (result.rowcount or 0):
            raise RuntimeError(f"没有命中任何行（id={ids[0]}，可能已被改动）")
        return

    if row.op == OP_DELETE_RECORD:
        result = await db.execute(
            delete(target.model).where(
                target.pk_col.in_(ids), target.user_col == uid
            )
        )
        if not (result.rowcount or 0):
            raise RuntimeError(f"没有命中任何行（id={ids}，可能已被改动）")
        return

    if row.op == OP_INSERT_RECORD:
        values = target.restorable(row.before)
        if not values:
            raise ValueError("账本里没有可插回的字段（before 为空）")
        # ⚠️ 归属由服务端认定，`restorable` 已把 user_id 挡在外面
        db.add(target.model(user_id=uid, **values))
        await db.flush()
        return

    if row.op == OP_RESTORE_MEMORY:
        restored = 0
        for memory_id in ids:
            if await memory_service.restore_memory(db, uid, int(memory_id)):
                restored += 1
        if not restored:
            raise RuntimeError(f"记忆行不存在（id={ids}，可能已被物理淘汰）")
        return

    raise ValueError(f"未知的撤销动作：{row.op!r}")


async def _apply_restore_tree(db: AsyncSession, row: AiAgentOpLog) -> None:
    """执行一次「整树重插」（题库 / 题目的物理删除回退）

    从账本的 `before` 取快照，交给 `bank_tree_snapshot.restore_snapshot` 逐条插回。

    ⚠️ 部分成功怎么办：`restore_snapshot` 是**逐条容错**的，可能插回 400 行、
    失败 2 行。这时**不能抛异常**（抛了就等于把已经插进去的 400 行也判失败，
    用户会看到「回退失败」但数据其实回来大半）。做法是：
      · 一行都没插进去 → 抛异常（真的失败）；
      · 插了一部分 → **正常返回**，并给 `row.reason` 打上 `partial_restored`，
        由 `rollback_turn` 把它归进 `partial` 清单（界面标「部分回退」+ 原因）。
    """
    from app.services.ai.agent import bank_tree_snapshot as snap

    snapshot = row.before or {}
    outcome = await snap.restore_snapshot(db, snapshot)

    if outcome.get("skipped"):
        raise RuntimeError(
            "删除时的数据快照不可用（"
            + str(outcome.get("reason") or "unknown")
            + "），无法恢复"
        )

    restored_map = outcome.get("restored") or {}
    failed = outcome.get("failed") or []

    if not restored_map:
        detail = "; ".join(
            f"{f.get('table')}#{f.get('id')} {f.get('error')}" for f in failed[:3]
        )
        raise RuntimeError(f"没有任何一行被恢复：{detail or '快照里没有可恢复的行'}")

    if failed and not row.reason:
        # 部分成功 → 让上层把这行归进 `partial` 而不是静默当全成功
        row.reason = "partial_restored"

    logger.info(
        "[rollback] 整树恢复 tool={} action={} 恢复={} 失败={}",
        row.tool,
        row.action,
        restored_map,
        len(failed),
    )


async def rollback_turn(
    db: AsyncSession,
    user_id: int,
    session_id: Optional[str],
    turn_id: str,
) -> Dict[str, Any]:
    """回退某个 `(user_id, session_id, turn_id)` 的**全部**写操作。

    返回（键名固定，前端按它渲染）::

        {
          "reverted": 3,                     # 成功执行的逆操作条数（含 partial 那些）
          "skipped":  [{"tool","action","reason","reasonText"}],   # undoable=False，一行没动
          "failed":   [{"tool","action","error"}],                 # 执行失败（可以重试）
          "partial":  [{"tool","action","reason","reasonText"}],   # 撤了，但只补回一部分
        }

    ⚠️ 调用方负责 `commit`（与 `question_write_service` 同一约定：本函数不开自己的会话）。
    唯一的例外是 `OP_RESTORE_MEMORY` —— 它复用 `memory_service.restore_memory`，
    而那个函数**内部会 commit**（既有实现，见其 docstring）。

    ⚠️ 幂等：`undone_at` 非空的行**跳过且不执行** → 第二次调用 `reverted=0`、数据一行不动。
    不可回退的行（`skipped`）每次都会被**如实列出**（它们没有被「撤过」，
    所以不能靠 `undone_at` 记住 —— 列出来是信息，不是副作用）。

    ⚠️ 一条失败不拖垮整轮：每条逆操作各自包 SAVEPOINT，失败只回滚它自己
    （不包的话这条失败会让事务进 aborted 状态，后面每条都会跟着报错）。
    """
    outcome: Dict[str, Any] = {"reverted": 0, "skipped": [], "failed": [], "partial": []}
    uid = int(user_id or 0)
    sid = str(session_id or "")
    tid = str(turn_id or "").strip()

    # ⚠️⚠️ 越权/灾难闸门：空 turn_id 或非法 uid **直接返回空**
    if uid <= 0:
        logger.warning("[rollback] 拒绝执行：user_id 非法（{}）", user_id)
        return outcome
    if not tid:
        logger.warning("[rollback] 拒绝执行：turn_id 为空（空值不许当通配符）")
        return outcome

    rows = (
        await db.execute(
            select(AiAgentOpLog)
            .where(
                AiAgentOpLog.user_id == uid,
                AiAgentOpLog.session_id == sid,
                AiAgentOpLog.turn_id == tid,
            )
            # 倒序：后写的先撤（先 create 再 update 时，必须先撤 update 再撤 create）
            .order_by(AiAgentOpLog.op_index.desc(), AiAgentOpLog.id.desc())
        )
    ).scalars().all()

    now = datetime.now()
    for row in rows:
        if row.undone_at is not None:
            continue  # 幂等：这一条已经撤过了（第二次点击 = 什么都不做）
        if not row.undoable or not row.op:
            outcome["skipped"].append(_skip_item(row))
            continue
        try:
            if row.op == OP_RESTORE_MEMORY:
                # ⚠️ 不能套 SAVEPOINT：`restore_memory` 内部 commit，
                #    套在 begin_nested 里会抛
                #    "Can't operate on closed transaction inside context manager"
                #    （数据已写、却判失败 —— 见 memory_manage 模块 docstring 的实测）
                await _apply(db, uid, row)
                row.undone_at = now
                await db.flush()
            else:
                async with db.begin_nested():
                    await _apply(db, uid, row)
                    row.undone_at = now
        except Exception as e:  # noqa: BLE001 - 单条失败继续后面的
            logger.warning(
                "[rollback] 逆操作失败 tool={} action={} op={}: {}",
                row.tool,
                row.action,
                row.op,
                e,
            )
            outcome["failed"].append(
                {
                    "tool": row.tool,
                    "action": row.action,
                    "error": f"{type(e).__name__}: {e}",
                }
            )
            continue

        outcome["reverted"] += 1
        if row.reason:
            # 撤了，但没完全撤（如知识库：库回来了、文档分块已物理删）→ 让界面标「部分回退」
            outcome["partial"].append(_skip_item(row))

    logger.info(
        "[rollback] session={} turn={} user={} → 撤了 {} / 跳过 {} / 失败 {} / 部分 {}",
        sid,
        tid,
        uid,
        outcome["reverted"],
        len(outcome["skipped"]),
        len(outcome["failed"]),
        len(outcome["partial"]),
    )
    return outcome


__all__ = [
    "REASON_TEXT",
    "record_op",
    "rollback_turn",
]
