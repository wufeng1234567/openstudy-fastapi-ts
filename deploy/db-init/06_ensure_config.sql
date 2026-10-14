-- ============================================================
-- 确保关键系统配置存在（幂等，可重复执行）
-- ------------------------------------------------------------
-- 用途：给「已建好的库」补上后来新增的配置项（全新建库由 01 脚本负责）。
-- 用法：psql -U root -d openstudy_v2_pgsql -f 06_ensure_config.sql
-- ============================================================

INSERT INTO public.sys_config (config_name, config_key, config_value, config_type, create_by, create_time, update_by, update_time, remark)
SELECT '系统-演示模式', 'sys.demo.mode', 'true', 'Y', 'admin', now(), '', NULL,
       '演示模式：true=登录页显示「演示账号一键登录」入口（自用/答辩）；false=上线体验版，直接走账号密码登录/注册，不暴露演示账号'
WHERE NOT EXISTS (SELECT 1 FROM public.sys_config WHERE config_key = 'sys.demo.mode');

-- 校验
SELECT config_id, config_key, config_value FROM public.sys_config WHERE config_key = 'sys.demo.mode';
