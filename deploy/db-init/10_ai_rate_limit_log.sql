-- ============================================================
-- AI 限流违规记录表 sys_ai_rate_limit_log（幂等，可重复执行）
-- ------------------------------------------------------------
-- 背景（2026-10）：后台「限流监控」页 —— 每次触发 AI 限流
--   （ip / user_min / user_day）写一行，供管理员查询与封禁决策。
-- 与 app/models/ai_rate_limit_log.py 同源：后端启动 create_all 也会建表，
-- 这里给 psql 手工部署路径一个等价的 SQL（表已存在则跳过）。
--
-- 用法：psql -U root -d openstudy_v2_pgsql -f 10_ai_rate_limit_log.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS public.sys_ai_rate_limit_log (
    id             BIGSERIAL PRIMARY KEY,
    user_id        BIGINT NULL,
    user_name      VARCHAR(64) NULL,
    ip             VARCHAR(64) NULL,
    path           VARCHAR(255) NULL,
    limit_type     VARCHAR(20) NULL,
    current_count  INTEGER NULL,
    limit_value    INTEGER NULL,
    create_time    TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_rl_log_user_time
    ON public.sys_ai_rate_limit_log (user_id, create_time);

CREATE INDEX IF NOT EXISTS idx_ai_rl_log_ip_time
    ON public.sys_ai_rate_limit_log (ip, create_time);

-- 校验
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'sys_ai_rate_limit_log'
ORDER BY ordinal_position;
