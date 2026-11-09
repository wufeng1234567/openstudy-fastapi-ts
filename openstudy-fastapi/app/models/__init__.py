# SQLAlchemy Models
from app.models.config import SysConfig
from app.models.ai_config import SysAiConfig
from app.models.ai_rate_limit_log import SysAiRateLimitLog
# 2026-10-27 聊天上传文件的持久化。此前附件是纯内存态（`AssistantAttachment`
# 的 docstring 明确写「不落存储」），导致「第二轮就取不到之前传的图」。
from app.models.chat_upload import ChatUploadFile, ChatUploadImage
# 0.4.x 资料知识网络：图片资产索引 + 统一内容引用
from app.models.content import ContentReference, RagImageAsset
# 0.4.1 真知识图谱：实体 + 有向关系 + 来源分块
from app.models.knowledge_graph import RagGraphEntity, RagGraphRelation
# 学习建议历史快照（只存建议，不存任务/完成态）
from app.models.study_plan import StudyPlanSnapshot
# 资料夹 ↔ 题库逻辑关联（不复制题库，只做引用）
from app.models.question_bank_link import QuestionBankKbLink
# 资料夹来源实体集处理状态（增量更新）
from app.models.source_graph_state import SourceGraphState
