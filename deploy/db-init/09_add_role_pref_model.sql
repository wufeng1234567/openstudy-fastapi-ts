-- ============================================================
-- 专家模型覆盖：ai_agent_role_pref 新增 model 列（幂等，可重复执行）
-- ------------------------------------------------------------
-- 背景（2026-10）：用户可给每个官方专家（题库/笔记/知识库/统计…）单独挑模型。
-- 存在 ai_agent_role_pref（用户 × 专家 偏好表）上，与 disabled 列共存：
--   · model 为 NULL = 跟随默认模型；
--   · model 非空 = 委派该专家时用这个模型（与 disabled 互不影响）。
-- 与 app/database.py 的 _ensure_agent_role_pref_columns 同源：后端启动也会补列，
-- 这里给 psql 手工部署路径一个等价的 SQL（列已存在则跳过）。
--
-- 用法：psql -U root -d openstudy_v2_pgsql -f 09_add_role_pref_model.sql
-- ============================================================

ALTER TABLE public.ai_agent_role_pref
    ADD COLUMN IF NOT EXISTS model VARCHAR(128) NULL;

-- 校验
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'ai_agent_role_pref'
  AND column_name = 'model';
