-- ============================================================
-- 19_material_asset_usage.sql
-- ------------------------------------------------------------
-- 「我的资料」图片资产用途账本（2026-10-29）
--
-- 图片被插入题目/笔记/文档时写一条记录；读取时按 asset_key 聚合。
-- asset_key：
--   · 文档内图片：doc:{docId}:{imageIndex}
--   · 聊天独立图片：chat:{imageId}
--
-- ⚠️ 应用启动时 `init_db()` 的 create_all 也会建这张表；本脚本用于
--    “只跑 db-init、不跑应用启动建表”的部署环境，保持两边一致。
-- ============================================================

CREATE TABLE IF NOT EXISTS material_asset_usage (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES sys_user(user_id),
    asset_key VARCHAR(120) NOT NULL,
    asset_url VARCHAR(500),
    target_type VARCHAR(20) NOT NULL,
    target_id BIGINT NOT NULL,
    deleted SMALLINT NOT NULL DEFAULT 0,
    create_time TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uk_material_asset_usage_target
        UNIQUE (user_id, asset_key, target_type, target_id)
);

CREATE INDEX IF NOT EXISTS idx_material_asset_usage_user
    ON material_asset_usage(user_id);

CREATE INDEX IF NOT EXISTS idx_material_asset_usage_asset
    ON material_asset_usage(asset_key);
