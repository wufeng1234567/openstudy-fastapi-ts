-- ============================================================
-- 24_material_organize_plan.sql
-- 智能整理：预览计划、深度整理阶段、剔除范围
-- ============================================================

ALTER TABLE rag_document
    ADD COLUMN IF NOT EXISTS excluded_ranges JSON NULL;

CREATE TABLE IF NOT EXISTS material_organize_plan (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES sys_user(user_id),
    doc_id BIGINT NOT NULL,
    mode VARCHAR(20) NOT NULL DEFAULT 'quick',
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    stage VARCHAR(30),
    progress INTEGER NOT NULL DEFAULT 0,
    base_revision VARCHAR(64),
    options_json JSON,
    plan_json JSON,
    summary_json JSON,
    error_msg VARCHAR(500),
    create_time TIMESTAMP DEFAULT now(),
    update_time TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_material_organize_plan_user
    ON material_organize_plan(user_id);
CREATE INDEX IF NOT EXISTS idx_material_organize_plan_doc
    ON material_organize_plan(doc_id);
