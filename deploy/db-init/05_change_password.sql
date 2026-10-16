-- ============================================================
-- 上线体验版 · 密码补丁
-- ------------------------------------------------------------
-- 把演示账号的密码统一改成强密码，防止别人乱登。
--   账号范围：admin / user1 / user2 / guest
--   新密码  ：***REMOVED***
-- 用法（在已初始化数据库上执行）：
--   psql -U root -d openstudy_v2_pgsql -f 05_change_password.sql
-- 说明：password 是 bcrypt 哈希（由后端 hash_password 生成，算法 $2b$12$）。
--       想换密码：用它跑 python -c "from app.core.security import hash_password; print(hash_password('新密码'))" 生成新哈希替换掉
-- ============================================================

UPDATE public.sys_user
SET password = '$2b$12$XCWtkQ37WqBbWgMklX2of.qe6Lps5fXh5ehMUr3zJ6fMe62QQahlW'
WHERE user_name IN ('admin', 'user1', 'user2', 'guest');

-- 校验：确认几个账号都存在且密码已更新
SELECT user_id, user_name, LEFT(password, 7) AS pwd_prefix FROM sys_user ORDER BY user_id;
