-- ============================================================
-- 23_document_searchable.sql
-- ------------------------------------------------------------
-- 单文档「可检索」开关（2026-10-29）
-- 0 = 可检索（默认，兼容历史数据）
-- 1 = 已屏蔽（不进入搜索/问答，但资料夹里仍可见）
-- ============================================================

ALTER TABLE rag_document
    ADD COLUMN IF NOT EXISTS disabled SMALLINT NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_rag_doc_searchable
    ON rag_document(kb_id, disabled);
