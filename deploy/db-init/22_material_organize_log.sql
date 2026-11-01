-- ============================================================
-- 22_material_organize_log.sql
-- ------------------------------------------------------------
-- 「我的资料」智能整理前后快照 / 回退批次（2026-10-29）
--
-- 每次整理（单文档或整资料夹）写一组 before/after JSON；
-- 用户查看 diff 后可整批回退。回退只标记 undone_at，不删除历史。
-- ============================================================

CREATE TABLE IF NOT EXISTS material_organize_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES sys_user(user_id),
    batch_id VARCHAR(64) NOT NULL,
    doc_id BIGINT NOT NULL,
    before_json JSON,
    after_json JSON,
    undone_at TIMESTAMP NULL,
    create_time TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_material_organize_user_batch
    ON material_organize_log(user_id, batch_id);

CREATE INDEX IF NOT EXISTS idx_material_organize_doc
    ON material_organize_log(doc_id);
