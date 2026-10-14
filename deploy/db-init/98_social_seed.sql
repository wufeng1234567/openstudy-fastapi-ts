-- ============================================================
-- OpenStudy 社交演示数据（评论 / 分享 / 通知）
-- ------------------------------------------------------------
-- 前置：先导入 01（结构）与 99（基础演示数据：user1/user2、题库、笔记）
-- 用法：psql -U root -d openstudy_v2_pgsql -f 98_social_seed.sql
-- ============================================================

SET client_encoding TO 'UTF8';

-- ---------- note_comment (评论：user2 评论 user1 的笔记) ----------
COPY public.note_comment (id, note_id, user_id, content, parent_id, reply_to_user_id, status, create_time) FROM stdin;
1	2	4	总结得很清楚，栈像摞盘子这个比喻很好记！	\N	\N	0	2026-10-13 10:20:00
2	2	3	谢谢，队列我一般记成排队打饭～	1	4	0	2026-10-13 10:25:00
3	3	4	三次握手讲得透彻，之前一直没搞懂为什么不能两次。	\N	\N	0	2026-10-12 15:40:00
4	4	4	排序对比表一目了然，收藏了。	\N	\N	0	2026-10-11 09:10:00
\.

UPDATE public.note SET comment_count = 2 WHERE note_id = 2;
UPDATE public.note SET comment_count = 1 WHERE note_id = 3;
UPDATE public.note SET comment_count = 1 WHERE note_id = 4;

-- ---------- bank_share (user1 把「数据结构基础」分享给 user2) ----------
COPY public.bank_share (id, bank_id, owner_id, share_token, share_code, permission, message, expire_time, receive_count, status, create_time, update_time) FROM stdin;
1	3	3	demo-share-token-0001	CS8K2M	readonly	数据结构复习题，拿去练练～	\N	1	0	2026-10-13 11:00:00	\N
\.

-- ---------- bank_share_receive (user2 领取) ----------
COPY public.bank_share_receive (id, share_id, bank_id, owner_id, receiver_id, source, status, create_time, update_time) FROM stdin;
1	1	3	3	4	share	0	2026-10-13 11:05:00	\N
\.

-- ---------- user_notification (站内通知) ----------
COPY public.user_notification (notification_id, user_id, notify_type, title, content, link, is_read, create_time) FROM stdin;
1	4	share_receive	你收到一个题库分享	用户「演示用户1」向你分享了题库《数据结构基础（演示题库）》	/front/myQuestion/myFavoriteBank	0	2026-10-13 11:05:00
2	3	system	欢迎使用 OpenStudy	欢迎体验 OpenStudy 学习平台，祝你学习愉快！	\N	0	2026-10-10 09:00:00
3	3	comment	收到新的评论	演示用户2 评论了你的笔记《栈与队列的区别》	/front/myQuestion/myNotes	1	2026-10-13 10:20:00
4	4	system	欢迎使用 OpenStudy	欢迎体验 OpenStudy 学习平台！	\N	1	2026-10-10 09:00:00
\.

-- 同步序列
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT table_name, column_name FROM information_schema.columns
    WHERE table_schema='public' AND column_default LIKE 'nextval(%'
  LOOP
    EXECUTE format('SELECT setval(pg_get_serial_sequence(''public.%I'',''%I''), COALESCE((SELECT MAX(%I) FROM public.%I),0)+1, false)', r.table_name, r.column_name, r.column_name, r.table_name);
  END LOOP;
END $$;
