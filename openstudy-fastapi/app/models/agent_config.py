"""
用户自定义智能体模型（多智能体协同，阶段 2）

表 `ai_agent_config` 存的是**用户自己创建并保存的智能体**（如「数学老师」「英语助教」）：

    · 人设提示词（`persona_prompt`）—— 该智能体的系统指令（英文，进 SystemMessage）；
    · 工具白名单（`tools`）—— 它**允许使用**的工具名数组（JSON）；
    · 可选绑定模型（`model`）—— 空 = 跟随用户默认模型；
    · 逻辑删除（`del_flag`）—— 与 `ai_agent_memory.del_flag` 同口径（'0' 未删 / '2' 已删）。

与「官方智能体」的区别（**别混**）
--------------------------------
官方角色（题库/笔记/知识库/…）住在 `services/ai/agent/roles.py` 的**代码常量表**里 ——
它们是平台产品定义，随代码版本走，不该让用户改，也不进数据库。

本表只存**用户数据**（用户自己建的智能体），因此需要持久化 + CRUD。
两者最终在编排层（`orchestrator.py`）汇合：都归约成「一组工具白名单 + 一段系统指令」。

建表约定（照抄 `agent_tool_pref.py` 的教训）
------------------------------------------
· 唯一索引名 `uk_ai_agent_config_user_name` **必须全库唯一**（PG 索引名是库级作用域）；
· 时间列 `create_time` / `update_time` **显式从 Python 传值，不用 `server_default`** ——
  否则 insert 后要 `refresh()` 才能读到，漏掉就抛 MissingGreenlet；
· 新模型**必须**加入 `app/database.py: register_all_models()` 的清单，否则 create_all
  不会建表（历史教训见那里的注释）。
"""

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import BigInteger, DateTime, Index, JSON, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 逻辑删除标记（与 `note.del_flag` / `agent_memory.del_flag` 同口径）
DEL_FLAG_NORMAL = "0"
DEL_FLAG_DELETED = "2"

#: 智能体名长度上限
MAX_NAME_LEN = 64
#: 人设提示词长度上限（太长没必要，只会挤占上下文；用户也不该靠它绕开系统规则）
MAX_PERSONA_LEN = 4000
#: 一个用户最多能建多少个自定义智能体（防滥用；与 `MAX_DOCS_PER_KB` 同类的额度闸门）
MAX_AGENTS_PER_USER = 50


class AiAgentConfig(Base):
    """用户自定义智能体"""

    __tablename__ = "ai_agent_config"
    __table_args__ = (
        Index(
            "uk_ai_agent_config_user_name",
            "user_id",
            "name",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: 归属用户。**只由登录态决定**（路由层只用 `current_user["user_id"]`，见 IDOR 红线）。
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: 智能体名（如「数学老师」）。同一用户下唯一（见上面的唯一索引）。
    name: Mapped[str] = mapped_column(String(MAX_NAME_LEN), nullable=False)
    #: 一句话简介（界面用）
    description: Mapped[Optional[str]] = mapped_column(String(255))
    #: 开场白（可选；用户点开该智能体时界面可显示）
    greeting: Mapped[Optional[str]] = mapped_column(String(500))
    #: 人设提示词（**英文**，进 SystemMessage）。用户填写，编排层注入到系统提示词。
    persona_prompt: Mapped[Optional[str]] = mapped_column(Text)
    #: 工具白名单（JSON 数组，元素是 `registry.names()` 里的工具名）。
    #: ⚠️ `None` / `[]` = **不限制**（等价于全部工具）—— 与官方 `general` 角色同语义。
    #: 用 JSON 列而非逗号串：工具名是受控集合，JSON 便于前端直接渲染多选。
    #: ⚠️ 注解用 `Any` 而非 `list`：SQLAlchemy 2.0 会按注解类型推断列类型，
    #:    写 `Mapped[Optional[list]]` 可能被推断成非 JSON 类型（实测建出了 text 列）。
    #:    显式 `mapped_column(JSON)` + `Mapped[Any]` 才能稳定产出 `json` 列。
    tools: Mapped[Any] = mapped_column(JSON)
    #: 可选绑定模型名（`sys_ai_config.model`）。空 = 跟随用户默认模型。
    model: Mapped[Optional[str]] = mapped_column(String(128))
    #: 是否启用（0 = 暂停，1 = 启用）。暂停后不出现在选择器里，但数据保留。
    is_enabled: Mapped[int] = mapped_column(SmallInteger, default=1)
    #: 逻辑删除（'0' 正常 / '2' 已删）。每个读点都必须显式带 `del_flag == '0'`。
    del_flag: Mapped[str] = mapped_column(String(1), default=DEL_FLAG_NORMAL)
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)


__all__ = [
    "AiAgentConfig",
    "DEL_FLAG_NORMAL",
    "DEL_FLAG_DELETED",
    "MAX_NAME_LEN",
    "MAX_PERSONA_LEN",
    "MAX_AGENTS_PER_USER",
]
