"""
AI 对话历史模型（SQL 存储）

替代原先的 Redis 实现：会话与消息都落库，重启 / 清缓存不丢，也便于查询统计。

- ai_chat_session：会话索引（会话列表、标题、消息数、最后更新时间）
- ai_chat_message：消息明细（role/content/attachments/turn_id/del_flag）
- ai_agent_timeline：智能体完整时间线快照（含工具调用卡片，供刷新后复原 UI）
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, DateTime, Integer, String, Text, Index
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

# 消息正文 / 附件元信息都用 MEDIUMTEXT（16MB）。
# 用 Text 的话 MySQL 落成 TEXT，上限只有 64KB —— 一张 240px 的缩略图
# base64 后约 30~50KB，多张图的 JSON 很容易超，写库会直接报
# (1406, "Data too long for column 'attachments'")，这一轮历史就丢了。
_LONG_TEXT = Text().with_variant(MEDIUMTEXT, "mysql")


class AiChatSession(Base):
    """AI 会话（会话列表的一行）"""

    __tablename__ = "ai_chat_session"

    # 直接用业务侧生成的 session_id 作主键，省掉一次映射查询
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, default=0)
    title: Mapped[Optional[str]] = mapped_column(String(100))
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)

    __table_args__ = (
        Index("idx_ai_chat_session_user", "user_id", "update_time"),
        # 必须显式声明 utf8mb4：库默认字符集可能是 utf8mb3（3 字节），
        # 存不下 emoji（4 字节 UTF-8），会报 (1366, "Incorrect string value")
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_general_ci"},
    )


class AiChatMessage(Base):
    """AI 会话中的一条消息"""

    __tablename__ = "ai_chat_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(BigInteger, default=0)
    # user / assistant / system
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[Optional[str]] = mapped_column(_LONG_TEXT)
    # 附件元信息（JSON 字符串）：[{name, type, thumb}]
    # 只存缩略图，不存原图，避免把表撑大
    attachments: Mapped[Optional[str]] = mapped_column(_LONG_TEXT)
    #: 这一条消息属于**哪一轮对话**（= 一次用户提问 + 它对应的一次回复）。
    #:   · api 付费链路：`AgentStreamRequest.turnId` 带上来（见 `loop.run_agent_stream`）；
    #:   · ds-free 链路：前端补写历史时带上来（`/ai/conversation/{sid}/messages` 的 `turnId`）；
    #:   · 普通助手链路（`chat_engine`）没有轮次概念 → **空串**；
    #:   · 历史行（加列之前写进去的）→ 空串。
    #: ⚠️ 空串**不是通配符**：回退按 `turn_id == <精确值>` 匹配，空值在端点与服务层
    #:    两层都被挡住（否则「缺参数」会变成「删光整个会话」）。
    turn_id: Mapped[str] = mapped_column(String(64), default="")
    #: 逻辑删除（口径与 `note.del_flag` / `ai_agent_memory.del_flag` **完全一致**）：
    #: `'0'` = 未删、`'2'` = 已删。用户点轮末「回退」= 把这一轮的两行置 `'2'`。
    #: ⚠️ 列是**后补**的（历史库靠 `database._ensure_ai_chat_message_columns` 加，
    #:    `create_all` 不会给已存在的表加列），所以**每一个读点都必须显式带
    #:    `del_flag == "0"`** —— 漏一处就是「回退掉了，模型还记得这一轮 / 刷新又回来了」
    #:    （读点清单见 `services/ai/conversation_service.py` 的模块 docstring）。
    del_flag: Mapped[str] = mapped_column(String(1), default="0")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)

    __table_args__ = (
        Index("idx_ai_chat_msg_session", "session_id", "id"),
        Index("idx_ai_chat_msg_user", "user_id", "id"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_general_ci"},
    )


class AiAgentTimeline(Base):
    """智能体「完整时间线」快照（一个会话一行）

    为什么需要它：
      `ai_chat_message` 只存「提问 + 最终回复」，**不含工具调用卡片**
      （tool_start / tool_result / 自我纠正等过程消息）—— 那些是渲染层的结构化数据。
      刷新后若只从消息行复原，卡片全没了、只剩纯文本（用户说的「死数据」）。
      这里把前端 `useAgentChat` 的**整条消息流**（含卡片字段）按会话存成一份 JSON 快照，
      加载时优先用它复原，卡片样式与状态就都还在。
    """

    __tablename__ = "ai_agent_timeline"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, default=0)
    # 前端消息流 JSON： [{role,type,content,tool,action,status,params,data,...}]
    payload: Mapped[Optional[str]] = mapped_column(_LONG_TEXT)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)

    __table_args__ = (
        Index("idx_ai_agent_timeline_user", "user_id", "update_time"),
        {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_general_ci"},
    )
