-- ============================================================
-- 工作空间（Workspace）· 2026-10-22
-- ------------------------------------------------------------
-- 设计：**复用 rag_knowledge_base**，不新建业务表。
--   每个用户有且只有一个「工作空间」知识库（is_workspace = 1），
--   用户往里丢的文件就是普通的 rag_document —— 分块、向量化、检索全部复用。
--
-- 为什么复用而不是新建：
--   · 工作空间里的文件本来就要被 AI 语义检索 → 与知识库是同一件事；
--   · 新建表会让「上传解析/分块/向量化」三套逻辑各写第二遍（早晚漂移）；
--   · AI 的 knowledge_search 工具不用改，天然能搜到工作空间里的文件。
--
-- 与普通知识库的区别只在**语义**：
--   · 工作空间是「用户的资料抽屉」，不参与「选哪个库来出题」的显式选择；
--   · 前端在侧栏单独入口展示，与「知识库」分开。
-- ============================================================

ALTER TABLE rag_knowledge_base
    ADD COLUMN IF NOT EXISTS is_workspace SMALLINT NOT NULL DEFAULT 0;

COMMENT ON COLUMN rag_knowledge_base.is_workspace IS
    '1=该用户的工作空间（每人一个，随用户创建）；0=普通知识库';

-- 每个用户最多一个工作空间：部分唯一索引兜底（应用层也会校验）
CREATE UNIQUE INDEX IF NOT EXISTS uk_kb_workspace_per_user
    ON rag_knowledge_base (user_id)
    WHERE is_workspace = 1 AND del_flag = '0';

-- 给工作空间里的文档加个「用户自定义标签」（可选，便于 AI 描述文件用途）
ALTER TABLE rag_document
    ADD COLUMN IF NOT EXISTS user_note VARCHAR(200);

COMMENT ON COLUMN rag_document.user_note IS
    '用户给这份资料写的一句话说明（如「高二期末卷」），AI 找文件时会参考';
