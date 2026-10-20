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
from app.services.ai.agent.tools.agent_manage import AgentManageTool
from app.services.ai.agent.tools.bank_export import BankExportTool
from app.services.ai.agent.tools.bank_manage import BankManageTool
from app.services.ai.agent.tools.bank_share_manage import BankShareManageTool
from app.services.ai.agent.tools.delegate import DelegateTaskTool
from app.services.ai.agent.tools.knowledge_base_manage import KnowledgeBaseManageTool
from app.services.ai.agent.tools.knowledge_ingest import KnowledgeIngestTool
from app.services.ai.agent.tools.knowledge_search import KnowledgeSearchTool
from app.services.ai.agent.tools.learning_stats import LearningStatsTool
from app.services.ai.agent.tools.memory_manage import MemoryManageTool
from app.services.ai.agent.tools.memory_search import MemorySearchTool
from app.services.ai.agent.tools.note_manage import NoteManageTool
from app.services.ai.agent.tools.question_manage import QuestionManageTool
from app.services.ai.agent.tools.question_mark_manage import QuestionFlagManageTool

# 幂等注册：重复 import 不会重复覆盖（registry.register 按 name 覆盖，行为一致）
registry.register(AgentManageTool())
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
# —— 2026-10-09 放行「从文本 / 附件写入知识库」能力（`knowledge_base_manage` 曾刻意封禁，
#    原因涉付费 embedding；本次按方案 B（解析落库同步 + 向量化后台）放行，见该模块 docstring）
registry.register(KnowledgeIngestTool())
# —— 2026-10-20 题库导出：把「页面上那个导出按钮」接进对话。
#    ⚠️ 它与 `bank_manage` 是**两个工具**而不是给 `bank_manage` 加一个 `export` action：
#    导出的产物是**文件**（要落盘、要下载链接），而 `bank_manage` 的每个 action 都在
#    改题库本身；混在一起会让「导出」被误当成一次写库操作，也让那个工具的描述更长
#    （描述越长，模型选错 action 的概率越高）。见 `bank_export.py` 模块说明。
registry.register(BankExportTool())
# —— 2026-10-09 指挥家模式：`delegate_task` 是**元工具**（指挥家把任务派给子代理）。
#    ⚠️ 它**不参与任何角色的工具白名单**：`orchestrator.compute_exclude` 会把它永远排除，
#    只有指挥家模式由 `loop` 单独挂上（防子代理递归委派）。见 delegate.py 模块说明。
registry.register(DelegateTaskTool())

__all__ = [
    "AgentManageTool",
    "BankExportTool",
    "BankManageTool",
    "BankShareManageTool",
    "DelegateTaskTool",
    "KnowledgeBaseManageTool",
    "KnowledgeIngestTool",
    "KnowledgeSearchTool",
    "LearningStatsTool",
    "MemoryManageTool",
    "MemorySearchTool",
    "NoteManageTool",
    "QuestionFlagManageTool",
    "QuestionManageTool",
]
