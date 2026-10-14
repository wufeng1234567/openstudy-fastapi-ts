-- ============================================================
-- OpenStudy 笔记分享数据（公开分区 + 公开笔记）
-- ------------------------------------------------------------
-- 前置：先导入 01（结构）、97（演示账号 user1/user2）
-- 用法：psql -U root -d openstudy_v2_pgsql -f 96_note_public_seed.sql
-- 幂等：开头会清掉本脚本插入的行，可重复执行
-- ============================================================

SET client_encoding TO 'UTF8';

-- 幂等清理
DELETE FROM public.note_question      WHERE note_id BETWEEN 2001 AND 2006;
DELETE FROM public.note_question_bank WHERE note_id BETWEEN 2001 AND 2006;
DELETE FROM public.user_note_favorite WHERE note_id BETWEEN 2001 AND 2006;
DELETE FROM public.note_comment       WHERE note_id BETWEEN 2001 AND 2006;
DELETE FROM public.note               WHERE note_id BETWEEN 2001 AND 2006;
DELETE FROM public.note_public_section WHERE id BETWEEN 1 AND 8;

-- ---------- note_public_section (笔记分享分区) ----------
COPY public.note_public_section (id, name, sort_order, create_time) FROM stdin;
1	Java	1	2026-01-01 00:00:00
2	Python	2	2026-01-01 00:00:00
3	前端	3	2026-01-01 00:00:00
4	后端	4	2026-01-01 00:00:00
5	数据库	5	2026-01-01 00:00:00
6	运维	6	2026-01-01 00:00:00
7	AI/大数据	7	2026-01-01 00:00:00
8	其他	99	2026-01-01 00:00:00
\.

-- ---------- note (公开笔记，用于「笔记分享」) ----------
COPY public.note (note_id, user_id, category_id, title, filename, content, markdown_content, tags, public_section_id, cover_image, is_public, view_count, like_count, comment_count, status, del_flag, create_time, update_time) FROM stdin;
2001	3	2	Java 集合框架：ArrayList vs LinkedList		ArrayList 底层是数组，随机访问 O(1)，尾部插入均摊 O(1)，中间插入需搬移元素 O(n)；LinkedList 底层是双向链表，随机访问 O(n)，头尾插入 O(1)。\n\n选型建议：绝大多数场景用 ArrayList（缓存友好、内存紧凑）；只有频繁在两端增删才考虑 LinkedList。	ArrayList 底层是数组，随机访问 O(1)，尾部插入均摊 O(1)，中间插入需搬移元素 O(n)；LinkedList 底层是双向链表，随机访问 O(n)，头尾插入 O(1)。\n\n选型建议：绝大多数场景用 ArrayList（缓存友好、内存紧凑）；只有频繁在两端增删才考虑 LinkedList。	Java,集合	1	\N	1	0	0	0	published	0	2026-03-01 09:00:00	\N
2002	3	2	Python 虚拟环境到底解决什么问题		虚拟环境把「项目依赖」与「系统 Python」隔离：不同项目可装不同版本的同一个包，互不污染。\n\n常用：python -m venv .venv 创建，激活后 pip install 只装进该环境。切记把 .venv 加入 .gitignore。	虚拟环境把「项目依赖」与「系统 Python」隔离：不同项目可装不同版本的同一个包，互不污染。\n\n常用：python -m venv .venv 创建，激活后 pip install 只装进该环境。切记把 .venv 加入 .gitignore。	Python,工程化	2	\N	1	0	0	0	published	0	2026-03-01 09:00:00	\N
2003	4	2	Vue3 组合式 API 的 ref 与 reactive 怎么选		ref 适合基本类型与「整体替换」的对象；reactive 适合天然的对象状态。\n\n注意：reactive 解构会丢失响应性，需要 toRefs；ref 在模板里自动解包，但在 JS 里要 .value。	ref 适合基本类型与「整体替换」的对象；reactive 适合天然的对象状态。\n\n注意：reactive 解构会丢失响应性，需要 toRefs；ref 在模板里自动解包，但在 JS 里要 .value。	Vue3,前端	3	\N	1	0	0	0	published	0	2026-03-01 09:00:00	\N
2004	3	2	MySQL 索引失效的几种常见情况		1) 对索引列做函数运算或隐式类型转换；2) 前导模糊 LIKE '%x'；3) OR 连接非索引列；4) 违反最左前缀。\n\n排查手段：EXPLAIN 看 type 是否退化成 ALL。	1) 对索引列做函数运算或隐式类型转换；2) 前导模糊 LIKE '%x'；3) OR 连接非索引列；4) 违反最左前缀。\n\n排查手段：EXPLAIN 看 type 是否退化成 ALL。	MySQL,数据库	5	\N	1	0	0	0	published	0	2026-03-01 09:00:00	\N
2005	4	2	Docker Compose 一键起多服务		用 docker-compose.yml 声明多个服务与依赖关系，docker compose up -d 一条命令全起。\n\n要点：服务间用「服务名」互访，数据用 named volume 持久化，首次可挂初始化脚本目录自动建库。	用 docker-compose.yml 声明多个服务与依赖关系，docker compose up -d 一条命令全起。\n\n要点：服务间用「服务名」互访，数据用 named volume 持久化，首次可挂初始化脚本目录自动建库。	Docker,运维	6	\N	1	0	0	0	published	0	2026-03-01 09:00:00	\N
2006	3	2	大模型 Prompt 编写的三个实用技巧		1) 给角色与目标：明确「你是谁、要做什么」；2) 给约束与格式：规定输出结构与边界；3) 给例子（少样本）：一两个示范胜过一堆描述。	1) 给角色与目标：明确「你是谁、要做什么」；2) 给约束与格式：规定输出结构与边界；3) 给例子（少样本）：一两个示范胜过一堆描述。	Prompt,AI	7	\N	1	0	0	0	published	0	2026-03-01 09:00:00	\N
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
