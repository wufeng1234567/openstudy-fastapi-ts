-- ============================================================
-- 线上真库清理补丁（演示账号口径统一）
-- ------------------------------------------------------------
-- 背景：线上库经过多次导入/迁移后，账号与种子口径出现漂移：
--   · user_id 2 = `ry`（01_deploy 原本是 `demo`，早被顶掉了）——死账号残留
--   · user_id 103 = `123`、104 = `1234` ——测试时随手建的杂账号
-- 本脚本把「演示账号」收敛到规范口径，并删掉这些杂账号（连同其内容数据）。
--
-- ⚠️ 逐字读完再执行。建议先跑「第 0 步干跑」看要删哪些。
-- ⚠️ 幂等：重复执行不报错（已删的再删是 no-op）。
-- ⚠️ 需要超级用户（本机 root / 线上 postgres）——第 1 步用了 session_replication_role。
-- 用法：
--   psql -U root -d openstudy_v2_pgsql -f 11_cleanup_users.sql
-- ============================================================

SET client_encoding TO 'UTF8';

-- ---------- 0. 干跑：先看当前账号，确认要删的确实是这些 ----------
SELECT user_id, user_name, nick_name, status, del_flag,
       CASE WHEN user_name IN ('admin','user1','user2','guest') THEN '保留' ELSE '将删除' END AS action
FROM public.sys_user
ORDER BY user_id;

BEGIN;

-- 临时关掉 FK 触发器：杂账号的内容可能散落在多张子表（含多层嵌套），
-- 逐个枚举既繁琐又易漏（实测漏掉 sys_notice_read 就会整段回滚）。
-- replica 角色下本会话不校验 FK，删完再还原。仅超级用户可用。
SET LOCAL session_replication_role = replica;

DO $$
DECLARE
  r record;
  junk_uids bigint[] := ARRAY(
    SELECT user_id FROM public.sys_user
    WHERE user_name IN ('123', '1234', 'ry', 'demo')
  );
BEGIN
  IF array_length(junk_uids, 1) IS NULL THEN
    RAISE NOTICE '没有要清理的杂账号（跳过按 uid 删除，仍会做孤儿清扫）';
  ELSE
    RAISE NOTICE '清理杂账号 user_id = %', junk_uids;
  END IF;

  -- 1) 用户直接归属的内容：枚举**所有带 `user_id` 列**的表（不依赖 FK ——
  --    实测 question_bank / user_practice_log / user_notification / ai_agent_* /
  --    ai_chat_* / leave_message 等**有 user_id 但没有指向 sys_user 的外键**，
  --    只按 FK 枚举会漏掉它们、留下孤儿数据）。
  --    排除 sys_user 本身（第 5 步单独删）。junk_uids 为空时 = no-op。
  FOR r IN
    SELECT table_name AS tbl
    FROM information_schema.columns
    WHERE column_name = 'user_id' AND table_schema = 'public'
      AND table_name <> 'sys_user'
  LOOP
    EXECUTE format('DELETE FROM public.%I WHERE user_id = ANY($1)', r.tbl) USING junk_uids;
  END LOOP;

  -- 2) 题库/题目（问/子题经 bank 关联，不是直接 user_id）
  DELETE FROM public.question_sub  WHERE main_id IN (SELECT id FROM public.question_main WHERE bank_id IN (SELECT id FROM public.question_bank WHERE user_id = ANY(junk_uids)));
  DELETE FROM public.question_main WHERE bank_id IN (SELECT id FROM public.question_bank WHERE user_id = ANY(junk_uids));

  -- 3) 笔记体系（note 已被第 1 步删；这里清它的子表，避免留孤儿）
  DELETE FROM public.note_question      WHERE note_id NOT IN (SELECT note_id FROM public.note);
  DELETE FROM public.note_question_bank WHERE note_id NOT IN (SELECT note_id FROM public.note);
  DELETE FROM public.note_comment       WHERE note_id NOT IN (SELECT note_id FROM public.note);
  DELETE FROM public.note               WHERE user_id = ANY(junk_uids);
  DELETE FROM public.note_category      WHERE user_id = ANY(junk_uids);

  -- 4) 知识库体系（rag_knowledge_base 已被第 1 步删；清其文档/分块孤儿）
  DELETE FROM public.rag_document_chunk WHERE doc_id NOT IN (SELECT id FROM public.rag_document);
  DELETE FROM public.rag_document       WHERE kb_id NOT IN (SELECT id FROM public.rag_knowledge_base);

  -- 5) 角色关联 + 用户本身
  DELETE FROM public.sys_user_role WHERE user_id = ANY(junk_uids);
  DELETE FROM public.sys_user      WHERE user_id = ANY(junk_uids);

  -- 6) 孤儿清扫：内容表里 user_id 已不在 sys_user 的行（历史删号留下的残渣）。
  --    ⚠️ 只在本次确实删过账号时才扫 —— 避免把「合法的、user_id 为空/NULL」的共享数据误删。
  FOR r IN
    SELECT table_name AS tbl
    FROM information_schema.columns
    WHERE column_name = 'user_id' AND table_schema = 'public'
      AND table_name <> 'sys_user'
  LOOP
    EXECUTE format(
      'DELETE FROM public.%I WHERE user_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM public.sys_user u WHERE u.user_id = public.%I.user_id)',
      r.tbl, r.tbl
    );
  END LOOP;
END $$;

SET LOCAL session_replication_role = DEFAULT;

-- ---------- 规范化演示账号 ----------
UPDATE public.sys_user SET status = '0', del_flag = '0'
WHERE user_name IN ('admin', 'user1', 'user2', 'guest');

-- 确保 admin 是管理员（role_id=1）
INSERT INTO public.sys_user_role (user_id, role_id)
SELECT u.user_id, 1 FROM public.sys_user u
WHERE u.user_name = 'admin'
  AND NOT EXISTS (SELECT 1 FROM public.sys_user_role r WHERE r.user_id = u.user_id AND r.role_id = 1);

COMMIT;

-- ---------- 复核 ----------
SELECT user_id, user_name, nick_name, status, del_flag
FROM public.sys_user ORDER BY user_id;
