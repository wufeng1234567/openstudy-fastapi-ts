"""
Agent 工具开关模型（用户 × 工具）

表 `ai_agent_tool_pref` 存的是「**这个用户屏蔽了哪些工具**」，采用**稀疏存储**：

- **没有行 = 启用**（产品口径：默认全部工具开启，用户自由选择）；
- 有行且 `disabled` 非零 = 该用户屏蔽了这个工具。

为什么是稀疏的、而不是每个用户预写全部工具的行：
工具是**会新增**的（注册表加一行就多一个），预写意味着「每加一个工具就要给所有
用户回填历史行」，漏一次就有人莫名其妙少一个工具；稀疏存储下新工具**天生就是启用**，
永不需要回填。`disabled` 列因此只承载「用户主动关掉」这一个信息。

⚠️ 唯一索引名 `uk_ai_agent_tool_pref_user_tool` 必须**全库唯一** —— PG 的索引名是
库级作用域（三条 `user_question_*` 表共用过 `uk_user_question`，导致 PG 建表直接失败）。
索引前缀是 `user_id`，所以「查某用户全部开关」也走它，不需要再建一个单列索引。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AiAgentToolPref(Base):
    """某个用户对某个 Agent 工具的开关（一行 = 一次「主动关掉 / 显式打开」）"""

    __tablename__ = "ai_agent_tool_pref"
    __table_args__ = (
        Index(
            "uk_ai_agent_tool_pref_user_tool",
            "user_id",
            "tool_name",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: 归属用户。**只由登录态决定**（见 api/v1/ai.py 的两个 /ai/agent/tools 处理器）
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: 工具名，与 `registry.names()` 完全一致（`String(64)` 足够：最长的是 question_manage）
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    #: 0 = 启用，1 = 已屏蔽。服务层写库前一律归一成 0/1（非零即屏蔽）
    disabled: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    # ⚠️ 时间列显式从 Python 传值，**不用 `server_default`** —— 用 server_default 的话
    #    insert 后必须 `refresh()` 才能读到值，漏掉就抛 MissingGreenlet（见
    #    backend-db-security 的「坑 4」）。这两个字段没有任何「让数据库填」的必要。
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)


__all__ = ["AiAgentToolPref"]
