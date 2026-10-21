-- ============================================================
-- AI 限流管理 菜单（系统监控 → AI 限流）
-- ------------------------------------------------------------
-- 对应后端 app/api/v1/rate_limit_admin.py（prefix /monitor/ratelimit）
-- 与前端 openstudy-vue3-ts/src/views/monitor/ratelimit/index.vue。
-- 菜单 id 用 115 起（109-114 已分配给监控下的其它页）。
-- 幂等：重复执行不报主键冲突。
-- 用法：
--   psql -U root -d openstudy_v2_pgsql -f 12_rate_limit_menu.sql
-- ============================================================

SET client_encoding TO 'UTF8';

-- 主菜单：类型 C（可点开的页面），挂在「系统监控」(menu_id=2) 下
INSERT INTO public.sys_menu
  (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
VALUES
  (115, 'AI 限流', 2, 10, 'ratelimit', 'monitor/ratelimit/index', '', 1, 0, 'C', '0', '0', 'monitor:ratelimit:list', 'rate', 'admin', now(), '', NULL, 'AI 限流配置 / 违规记录 / 计数器 / 封禁')
ON CONFLICT (menu_id) DO NOTHING;

-- 按钮权限（类型 F）
INSERT INTO public.sys_menu
  (menu_id, menu_name, parent_id, order_num, path, component, query, is_frame, is_cache, menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark)
VALUES
  (116, '限流查询', 115, 1, '#', '', NULL, 1, 0, 'F', '0', '0', 'monitor:ratelimit:query',  '#', 'admin', now(), '', NULL, ''),
  (117, '限流修改', 115, 2, '#', '', NULL, 1, 0, 'F', '0', '0', 'monitor:ratelimit:edit',   '#', 'admin', now(), '', NULL, '改配置 / 清计数器 / 封禁'),
  (118, '限流删除', 115, 3, '#', '', NULL, 1, 0, 'F', '0', '0', 'monitor:ratelimit:remove', '#', 'admin', now(), '', NULL, '')
ON CONFLICT (menu_id) DO NOTHING;

-- 授权给超级管理员角色（role_id=1）
INSERT INTO public.sys_role_menu (role_id, menu_id) VALUES (1, 115), (1, 116), (1, 117), (1, 118)
ON CONFLICT DO NOTHING;

-- 复核
SELECT menu_id, menu_name, parent_id, path, component, perms, menu_type FROM public.sys_menu WHERE menu_id BETWEEN 115 AND 118 ORDER BY menu_id;
