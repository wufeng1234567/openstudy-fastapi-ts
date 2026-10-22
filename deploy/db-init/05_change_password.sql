-- ============================================================
-- 演示账号 · 初始密码补丁
-- ------------------------------------------------------------
-- 把演示账号的密码统一设置为本地体验用的初始密码。
--   账号范围：admin / user1 / user2 / guest
--   初始密码：123456
--
-- ⚠️ 这只是**本地快速体验**用的弱密码。
--    正式对外部署前，请务必改成强密码（见下方「如何换密码」）。
--
-- 用法（在已初始化数据库上执行）：
--   psql -U root -d openstudy_v2_pgsql -f 05_change_password.sql
--
-- 如何换密码：
--   cd openstudy-fastapi
--   python -c "from app.core.security import hash_password; print(hash_password('你的新密码'))"
--   把输出的 $2b$12$... 哈希串替换掉下面 UPDATE 语句里的值，再执行一次。
-- ============================================================

UPDATE public.sys_user
SET password = '$2b$12$BlEgzeesBqbIQV./peaGHeL/hpDHjoWz99FWimY.o1vZ5BOa72mLK'
WHERE user_name IN ('admin', 'user1', 'user2', 'guest');

-- 校验：确认几个账号都存在且密码已更新
SELECT user_id, user_name, LEFT(password, 12) AS pwd_prefix FROM sys_user ORDER BY user_id;
