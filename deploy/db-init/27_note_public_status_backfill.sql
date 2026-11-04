-- 2026-11-03: 公开笔记历史数据补 status='published'
-- 旧编辑器只写 is_public=1、没写 status，导致公开列表按 published 过滤后为空。
UPDATE note
SET status = 'published'
WHERE is_public = 1
  AND (status IS NULL OR status = '' OR status <> 'published');
