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
from app.services.ai.agent.tools.document_compose import DocumentComposeTool
from app.services.ai.agent.tools.document_compare import DocumentCompareTool
from app.services.ai.agent.tools.english_practice import EnglishPracticeTool
from app.services.ai.agent.tools.english_wordbook import EnglishWordbookTool
from app.services.ai.agent.tools.knowledge_base_manage import KnowledgeBaseManageTool
from app.services.ai.agent.tools.knowledge_ingest import KnowledgeIngestTool
from app.services.ai.agent.tools.knowledge_search import KnowledgeSearchTool
from app.services.ai.agent.tools.learning_stats import LearningStatsTool
from app.services.ai.agent.tools.memory_manage import MemoryManageTool
from app.services.ai.agent.tools.memory_search import MemorySearchTool
from app.services.ai.agent.tools.note_manage import NoteManageTool
from app.services.ai.agent.tools.question_manage import QuestionManageTool
from app.services.ai.agent.tools.question_mark_manage import QuestionFlagManageTool
from app.services.ai.agent.tools.review_sheet import ReviewSheetTool
from app.services.ai.agent.tools.workspace_search import WorkspaceSearchTool

# 幂等注册：重复 import 不会重复覆盖（registry.register 按 name 覆盖，行为一致）
registry.register(AgentManageTool())
registry.register(BankManageTool())
registry.register(NoteManageTool())
registry.register(QuestionManageTool())
registry.register(KnowledgeSearchTool())
# —— 2026-10-22 工作空间：按文件名 / 备注 / 正文找「用户空间里的那份资料」。
#    与 knowledge_search 分工：这个找**文件**（返回 docId），那个找**正文片段**。
#    用户说「用那份概率论的资料出题」时，先用这个定位文件，再用 knowledge_search 读内容。
registry.register(WorkspaceSearchTool())
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
# —— 2026-10-26 英语词库：把「英语学习」那几个页面接进对话。
#    ⚠️ 在此之前 15 个工具里**没有一个碰词库**，于是用户在聊天里问
#    「我在背什么词」「帮我加几个四级词」智能体只能答"做不到" ——
#    英语模块与对话是两座孤岛。这个工具让两边互通：
#        聊天说「加词」→ 写库 + 返回 jumpUrl → 前端渲染「去看看」卡片
#        → 用户点进去看到刚加的词 → 再点「去听写」，闭环成立。
registry.register(EnglishWordbookTool())
# —— 2026-10-26 英语练习记录：与 `english_wordbook` 配对。
#    ⚠️ 两者刻意分开（而不是给 wordbook 加几个 action）：
#      · wordbook 管**静态资产**（有哪些词书、里面有什么词）；
#      · practice 管**动态记录**（练了几次、错在哪）。
#    混在一起会让「我在背什么」（高频、只读）和「我练得怎么样」
#    （另一张表、另一个心智模型）挤进同一份描述，模型选错 action 的概率上升。
#    这也与 `learning_stats` / `bank_manage` 的分工口径一致。
registry.register(EnglishPracticeTool())
# —— 2026-10-26 复习卷：把「按薄弱点生成复习卷」接进对话。
#    ⚠️ 在此之前 REST 接口与页面按钮都有了，但**聊天里没有工具**。实测用户说
#    「帮我按薄弱点生成一份复习卷」，模型找不到工具就自己想办法：委派给「题库专家」
#    子代理去新建一个题库再把题复制进去 —— 跑了 180 秒还没完（实测直接超时），
#    而且**凭空改了用户数据**。用户想要的只是一份能打印的文件。
#    这个工具给模型一条正确的路，与 `bank_export` 同类（产物是文件，不是查询）。
registry.register(ReviewSheetTool())
# —— 2026-10-27 文档编排：让用户通过对话产出排版好的 Word / PDF。
#    ⚠️ 它与 `bank_export` 是**两个工具**，不能合并成 action：
#      · `bank_export` 的数据源是**数据库里的题库**（参数是 `bank_id`）；
#      · `document_compose` 的数据源是**用户给的任意内容**
#        （口述文字 / AI 生成的结构 / 已上传的文件），产物是通用文档。
#    混在一起的后果：模型在"用户想要一份通用文档"时去传 `bank_id`，
#    然后报错重试，白烧一轮 token。
#
#    它解决的场景是「用户给一段文字或一个混乱的 Word，我们重新排版」——
#    在此之前这件事只能靠模型自己拼 Markdown 然后什么都干不了。
registry.register(DocumentComposeTool())
# —— 2026-10-27 文档对比：让用户能问"这两份文件有什么区别"。
#    ⚠️ 差异必须由**确定性引擎**算（doc_compare_service），不能让模型自己读两份
#       长文档去比：漏一行、看错一个数字，用户几乎发现不了。
#    模型负责解释结论，不负责找差异。
registry.register(DocumentCompareTool())

__all__ = [
    "AgentManageTool",
    "BankExportTool",
    "BankManageTool",
    "BankShareManageTool",
    "DelegateTaskTool",
    "DocumentComposeTool",
    "DocumentCompareTool",
    "EnglishPracticeTool",
    "EnglishWordbookTool",
    "KnowledgeBaseManageTool",
    "KnowledgeIngestTool",
    "KnowledgeSearchTool",
    "LearningStatsTool",
    "MemoryManageTool",
    "MemorySearchTool",
    "NoteManageTool",
    "QuestionFlagManageTool",
    "QuestionManageTool",
    "ReviewSheetTool",
    "WorkspaceSearchTool",
]
