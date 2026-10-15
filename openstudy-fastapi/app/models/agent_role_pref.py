"""
Agent 专家（官方角色）开关模型（用户 × 专家）

表 `ai_agent_role_pref` 存的是「**这个用户关掉了哪些专家**」，采用**稀疏存储**：

- **没有行 = 启用**（产品口径：默认全部专家开启，用户自由选择关闭）；
- 有行且 `disabled` 非零 = 该用户关闭了这个专家。

与 `ai_agent_tool_pref` 的关系
------------------------------
`ai_agent_tool_pref` 是**工具粒度**的开关（用户直接开关「某个工具」）—— 但它对普通用户
没意义（用户不知道 `bank_manage` 是啥）。按用户 2026-10-10 裁决，界面上的开关上移到
**专家粒度**：用户开关的是「题库专家 / 笔记专家 / …」这类他能理解的**角色**，而不是技术工具。

本表因此是「用户禁用哪些专家」的稀疏记录。**关闭某专家**的效果 = 指挥家的子代理通讯录里
不再出现它（LLM 自然知道「叫不到这个专家」），且显式路由也不会落到它。

⚠️ 唯一索引名 `uk_ai_agent_role_pref_user_role` 必须**全库唯一**（PG 索引名是库级作用域）。
索引前缀是 `user_id`，故「查某用户全部专家开关」也走它，无需再建单列索引。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AiAgentRolePref(Base):
    """某个用户对某个官方专家（角色）的开关（一行 = 一次「主动关掉 / 显式打开」）"""

    __tablename__ = "ai_agent_role_pref"
    __table_args__ = (
        Index(
            "uk_ai_agent_role_pref_user_role",
            "user_id",
            "role_key",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: 归属用户。**只由登录态决定**
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: 专家 key（官方角色 key，如 bank/note/kb/stats；与 `roles.OFFICIAL_ROLES` 一致）
    role_key: Mapped[str] = mapped_column(String(32), nullable=False)
    #: 0 = 启用，1 = 已关闭。服务层写库前一律归一成 0/1（非零即关闭）
    disabled: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=text("0")
    )
    # ⚠️ 时间列显式从 Python 传值，**不用 `server_default`**（见 tool_pref 同款说明）。
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)


__all__ = ["AiAgentRolePref"]
