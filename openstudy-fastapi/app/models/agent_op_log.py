"""
Agent 写操作账本模型（`ai_agent_op_log`）

**一行 = 一次成功的写操作**。用户点「回退这一轮」时，`rollback_service.rollback_turn`
按 `(user_id, session_id, turn_id)` 把这一轮的行**倒序**执行它们的逆操作。

为什么需要它（今天后端没有任何「这一轮写了什么」的记录）
--------------------------------------------------------
实测（2026-09-22 只读调研，报告见 `.codebuddy` 外的那份给 team-lead 的研究报告）：
  · 事件流里**没有轮次标识**（只有 meta/text/tool_start/tool_result/done…）；
  · `ai_chat_message` 只存「提问 + 最终回复」，工具调用/参数/结果**完全不落库**；
  · `ai_agent_timeline` 是前端每轮**覆盖写**的整会话快照（无轮次、还会被瘦身截断）；
  · 全库只有 `logger.info` 级别的「操作日志」中间件，**没有任何写审计表**。
所以「一轮执行了哪些写操作」在后端是**不可追溯**的 —— 这张表就是补这个缺口。

轮次标识从哪来（⚠️ 后端不定义轮边界）
------------------------------------
`turn_id` 由**前端**每轮生成、在请求体里带上来（同一轮里的多次 ds-free 单次执行共用同一个）。
后端只负责「原样记账 + 在 `meta` 事件里回显」，**不自己切分轮边界** —— 轮边界在前端
（`useAgentChat` 一次 `runStream` = 一轮）。
兜底：请求没带 `turn_id` 时由 `loop._resolve_turn_id` 生成 `auto_<hex>`（**一次请求一个**）。
api 链路「一次请求 = 一轮」，所以兜底恰好等于正确粒度；ds-free 是多次请求共一轮，
兜底会退化成「一次工具调用一个 turn_id」—— 属于**安全退化**（回退按钮那一轮只能退回最后一次，
而不是把整轮的行扫进来）。⚠️ 空字符串**绝不许**当通配符用（见 `rollback_turn` 的守卫）。

`op_index` 的口径
----------------
同一 `(user_id, session_id, turn_id)` 内**自增**序号（写入时 `MAX(op_index)+1`），
回退时倒序执行 —— 后写的先撤，才不会出现「先撤 create 再撤 update」这种顺序错误。
选择 `MAX+1` 而不是「行数+1」：行数会被任何删除/回填打乱，而 MAX 只增；
并发同 turn 的两次请求理论上可能拿到同一个值，所以回退排序是
`op_index DESC, id DESC`（`id` 兜底，顺序仍然确定）。

⚠️ 表名/索引名的 PG 陷阱
------------------------
PG 的索引名是**库级唯一**的（三张 `user_question_*` 表共用过 `uk_user_question` 导致建表失败），
所以索引前缀写成完整的 `idx_ai_agent_op_log_*`。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AiAgentOpLog(Base):
    """一次写操作的账本行（含「怎么撤」的说明与改前状态）"""

    __tablename__ = "ai_agent_op_log"
    __table_args__ = (
        # 回退的唯一查询形状：某用户 + 某会话 + 某一轮
        Index("idx_ai_agent_op_log_turn", "user_id", "session_id", "turn_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: 归属用户。**只由服务端认定的登录态决定**，绝不接受请求体里的值（IDOR 红线）
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: 会话 id；无会话（未落库的临时对话）时为 `""`，不留 NULL（比较起来省事，且
    #: NULL 在 SQL 里 `==` 永远不为真，会静默退化成「查不到」）
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    #: 轮次 id（前端生成；缺省时后端给 `auto_<hex>` —— 见模块 docstring）
    turn_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    #: 同 turn 内序号（越大越新；回退按它倒序）
    op_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: 工具名（与注册表一致）
    tool: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    #: 工具的参数 action（回执与卡片都用它说「你刚才做的是删除/更新」）
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    #: **撤销动作名**（取值域见 `base.OP_*`）。不可回退时为空串
    op: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    #: 撤销要动的表（ORM 表名，取值域经 `rollback_service._TABLES` 白名单校验）
    target_table: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    #: 目标行 id 列表（JSON 数组）。批量操作（delete_many / clear）也走它
    target_ids: Mapped[Optional[list]] = mapped_column(JSON)
    #: **改前状态**（JSON 对象，字段名 = 目标表的列名）。
    #: ⚠️ 只放「恢复必需」的字段，不存整行；更新类没有它就无法回退（`op='restore_fields'`）
    before: Mapped[Optional[dict]] = mapped_column(JSON)
    #: 这条到底能不能撤。**默认 False**（工具没声明 = 不可撤，宁可为空绝不谎报）
    undoable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: 不可回退 / 部分回退的原因码（取值域见 `base.REASON_*`，中文文案见
    #: `rollback_service.REASON_TEXT`）。`undoable=True` 且 reason 非空 = **部分回退**
    reason: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    #: 已被回退的时间戳。**非空 = 不许再执行**（幂等的判据，也是「这一次撤销」的留痕）
    undone_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    #: 账本行自己的创建时间。由 Python 传值（不用 `server_default`: 那需要 refresh，
    #: 漏了就是 MissingGreenlet，见 backend-db-security 的坑 4）
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)


__all__ = ["AiAgentOpLog"]
