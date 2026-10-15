"""
Agent 长期记忆模型

对应表 `ai_agent_memory`（SpringBoot 时代建的表，结构沿用）。
v2 此前**没有任何代码读它** —— 27 行遗留数据一直是死的。

记忆分两类（`memory_type`）
---------------------------
- `episodic`：**做了什么**。「用户删除了题库「X」(ID=3)」这类具体操作记录。
  importance 高（删除 8 / 其它写操作 7），因为它承载事实、可用于追溯。
- `conversation`：**聊了什么**。一轮对话的摘要。importance 6。

⚠️ importance 只用于**排序与展示**，**不再用于淘汰**。
   legacy 的淘汰逻辑是「取全部类型总条数，超限就按 importance 升序删」，
   于是 conversation（6）会先于 episodic（7/8）被清掉 —— 对话摘要反而最先丢。
   这里改成**按类型分别限额**（见 `services/ai/memory_service.py`）。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

#: 记忆类型
MEMORY_TYPE_EPISODIC = "episodic"
MEMORY_TYPE_CONVERSATION = "conversation"

MEMORY_TYPES = (MEMORY_TYPE_EPISODIC, MEMORY_TYPE_CONVERSATION)

#: importance 取值范围（legacy 用 6/7/8，这里留宽一点）
IMPORTANCE_MIN = 1
IMPORTANCE_MAX = 10

#: 各类记忆的**独立**条数上限。刻意分开 —— 这正是修正 legacy 淘汰 bug 的地方。
MAX_PER_TYPE = {
    MEMORY_TYPE_EPISODIC: 200,
    MEMORY_TYPE_CONVERSATION: 50,
}

#: 单条记忆内容上限（表里是 text，但太长的记忆没有检索价值，只会挤占上下文）
MEMORY_CONTENT_MAX = 500


class AiAgentMemory(Base):
    """用户长期记忆"""

    __tablename__ = "ai_agent_memory"
    __table_args__ = (
        # 取「某用户某类型最近 N 条」是最常见的查询
        Index("idx_agent_memory_user_type", "user_id", "memory_type", "create_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_user.user_id"), nullable=False
    )
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # ⚠️ 列名是 `metadata` —— 而 `metadata` 在 SQLAlchemy 声明式里是保留名，
    #    所以属性叫 meta_data，显式映射到列名 metadata。写成属性名 metadata 会直接报错。
    meta_data: Mapped[Optional[dict]] = mapped_column("metadata", JSON)
    importance: Mapped[int] = mapped_column(Integer, default=5)
    # 逻辑删除（口径与 `note.del_flag` 一致）：`'0'` = 未删、`'2'` = 已删（可恢复）。
    # ⚠️ 列是**后补**的（历史库靠 `database._ensure_agent_memory_columns` 加，`create_all`
    #    不会给已存在的表加列），所以**每一个读点都必须显式带 `del_flag == "0"`** ——
    #    漏一处就是「删掉还搜得到 / 还占配额」（见 `services/ai/memory_service.py` 的清单）。
    del_flag: Mapped[str] = mapped_column(String(1), default="0")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "memoryId": self.id,
            "memoryType": self.memory_type,
            "content": self.content,
            "importance": self.importance,
            "metadata": self.meta_data,
            "createTime": self.create_time.isoformat(sep=" ") if self.create_time else None,
        }
