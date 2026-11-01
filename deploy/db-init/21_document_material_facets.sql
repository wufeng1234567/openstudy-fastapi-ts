-- ============================================================
-- 21_document_material_facets.sql
-- ------------------------------------------------------------
-- 「我的资料」文件智能整理字段（2026-10-29）
--
-- file_name 可以是整理后的展示名；original_file_name 保留用户上传原名。
-- subject / material_type / facets 是规则化整理结果，不是检索权限。
-- ============================================================

ALTER TABLE rag_document
    ADD COLUMN IF NOT EXISTS original_file_name VARCHAR(255) NULL,
    ADD COLUMN IF NOT EXISTS subject VARCHAR(50) NULL,
    ADD COLUMN IF NOT EXISTS material_type VARCHAR(30) NULL,
    ADD COLUMN IF NOT EXISTS facets JSON NULL;
