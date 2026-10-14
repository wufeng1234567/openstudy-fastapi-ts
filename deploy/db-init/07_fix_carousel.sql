-- ============================================================
-- 修复轮播图数据（把 image_url 指向随镜像打包的 /carousel-static/ 图片）
-- ------------------------------------------------------------
-- 背景：早期库里的 carousel.image_url 指向 /profile/upload/...（那些文件不在），
--       会 404。本脚本改为指向后端 /carousel-static/ 路由提供的预置图片。
-- 用法：psql -U root -d openstudy_v2_pgsql -f 07_fix_carousel.sql
-- 幂等：可重复执行。
-- ============================================================

DELETE FROM public.carousel;
INSERT INTO public.carousel (id, title, image_url, link_url, sort_order, status, create_time) VALUES
 (1, '自习室地图',   '/carousel-static/carousel-1.jpg', NULL, 0, '0', now()),
 (2, 'AI 学习周报',  '/carousel-static/carousel-2.jpg', NULL, 1, '0', now()),
 (3, '学习资料库',   '/carousel-static/carousel-3.jpg', NULL, 2, '0', now()),
 (4, 'AI 智能答疑',  '/carousel-static/carousel-4.jpg', NULL, 3, '0', now()),
 (5, '学习计划管理', '/carousel-static/carousel-5.jpg', NULL, 4, '0', now());
SELECT setval('public.carousel_id_seq', (SELECT MAX(id) FROM public.carousel));

-- 校验
SELECT id, title, image_url FROM public.carousel ORDER BY sort_order;
