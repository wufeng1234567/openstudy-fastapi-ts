-- 2026-11-04：我的资料支持同名版本化
-- rag_document.version：同名资料再次上传时递增（旧正文快照进 material_organize_log）
ALTER TABLE rag_document
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;

COMMENT ON COLUMN rag_document.version IS '资料版本号：同名资料再次上传时递增';
