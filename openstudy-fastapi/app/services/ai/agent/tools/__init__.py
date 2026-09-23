"""
Agent 内置工具集

导入本模块即完成注册（幂等）。新增工具 = 在这里加一行注册，别的地方都不用改：

    from app.services.ai.agent.registry import registry
    from app.services.ai.agent.tools.bank_manage import BankManageTool

    registry.register(BankManageTool())

工具的**描述与参数 schema 只写在工具类里**，注册表会把它同时喂给
原生 Function Calling 与（未来的）提示词协议，两边不会漂移。
"""

from app.services.ai.agent.registry import registry
from app.services.ai.agent.tools.bank_manage import BankManageTool
from app.services.ai.agent.tools.bank_share_manage import BankShareManageTool
from app.services.ai.agent.tools.knowledge_base_manage import KnowledgeBaseManageTool
from app.services.ai.agent.tools.knowledge_search import KnowledgeSearchTool
from app.services.ai.agent.tools.learning_stats import LearningStatsTool
from app.services.ai.agent.tools.memory_manage import MemoryManageTool
from app.services.ai.agent.tools.memory_search import MemorySearchTool
from app.services.ai.agent.tools.note_manage import NoteManageTool
from app.services.ai.agent.tools.question_manage import QuestionManageTool
from app.services.ai.agent.tools.question_mark_manage import QuestionFlagManageTool

# 幂等注册：重复 import 不会重复覆盖（registry.register 按 name 覆盖，行为一致）
registry.register(BankManageTool())
registry.register(NoteManageTool())
registry.register(QuestionManageTool())
registry.register(KnowledgeSearchTool())
registry.register(MemorySearchTool())
# —— 2026-09-22 补齐的五组能力（记忆管理 / 学习统计 / 题目标记 / 知识库管理 / 分享复制）= 5 个工具
#    ⚠️ 错题本 / 收藏 / 斩题是**一个**工具（`question_flag_manage`，用 flag_type 区分）——
#    三张表同一形状、领域层同一份实现，拆三个工具只是把同一段描述抄三遍、
#    把工具清单撑长（选错概率随清单变长而上升）。理由见该模块 docstring。
registry.register(MemoryManageTool())
registry.register(LearningStatsTool())
registry.register(QuestionFlagManageTool())
registry.register(KnowledgeBaseManageTool())
registry.register(BankShareManageTool())

__all__ = [
    "BankManageTool",
    "BankShareManageTool",
    "KnowledgeBaseManageTool",
    "KnowledgeSearchTool",
    "LearningStatsTool",
    "MemoryManageTool",
    "MemorySearchTool",
    "NoteManageTool",
    "QuestionFlagManageTool",
    "QuestionManageTool",
]
