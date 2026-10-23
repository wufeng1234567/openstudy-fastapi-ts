-- ============================================================
-- 16_english_seed.sql
-- ------------------------------------------------------------
-- 英语功能演示词书（2026-10-23）
--
-- 背景：`word_books` / `words` 实测都是 **0 行**。一个功能点进去
-- 空空如也，既没法演示也没法自测。这里补两本真实可用的词书。
--
-- 归属：挂在 user1（uid=105，演示用户）名下。
--       `user_id IS NULL` 表示"系统预置、所有人只读可见"，
--       这里**不**这么做 —— 预置书用户删不掉，容易让人困惑；
--       挂给演示账号更贴近真实使用。
--
-- 幂等：先按书名删掉旧数据再插入，可重复执行。
-- ============================================================

SET client_encoding TO 'UTF8';

DELETE FROM public.words
WHERE book_id IN (SELECT book_id FROM public.word_books WHERE book_name IN ('四级核心词', '考研高频词'));

DELETE FROM public.word_books WHERE book_name IN ('四级核心词', '考研高频词');

-- ---------- 词书 ----------
WITH ins AS (
  INSERT INTO public.word_books (user_id, book_name, book_description, word_count, status, del_flag, create_time)
  VALUES (105, '四级核心词', '大学英语四级高频词，含音标与例句', 12, '0', '0', '2026-10-20 10:00:00')
  RETURNING book_id
)
INSERT INTO public.words (book_id, word, phonetic, translation, example, sort_order, create_time)
SELECT book_id, v.word, v.phonetic, v.translation, v.example, v.ord, '2026-10-20 10:00:00'
FROM ins, (VALUES
  ('abandon',      'əˈbændən',      'v. 放弃；抛弃',        'He abandoned the plan at the last minute.', 1),
  ('benefit',      'ˈbenɪfɪt',      'n. 益处 v. 受益',      'Regular exercise benefits your health.', 2),
  ('campaign',     'kæmˈpeɪn',      'n. 运动；战役',        'They launched a campaign against plastic waste.', 3),
  ('deadline',     'ˈdedlaɪn',      'n. 最后期限',          'The deadline for the essay is Friday.', 4),
  ('efficient',    'ɪˈfɪʃnt',       'adj. 高效的',          'This algorithm is far more efficient.', 5),
  ('fluctuate',    'ˈflʌktʃueɪt',   'v. 波动；起伏',        'Prices fluctuate with demand.', 6),
  ('generate',     'ˈdʒenəreɪt',    'v. 产生；生成',        'The system can generate questions automatically.', 7),
  ('hesitate',     'ˈhezɪteɪt',     'v. 犹豫',              'Do not hesitate to ask for help.', 8),
  ('isolate',      'ˈaɪsəleɪt',     'v. 隔离；孤立',        'The defect was isolated to one module.', 9),
  ('justify',      'ˈdʒʌstɪfaɪ',    'v. 证明…正当',         'Nothing can justify such waste.', 10),
  ('maintain',     'meɪnˈteɪn',     'v. 维持；保养',        'Maintaining a clean codebase takes effort.', 11),
  ('notion',       'ˈnəʊʃn',        'n. 概念；想法',        'He had no notion of the risk involved.', 12)
) AS v(word, phonetic, translation, example, ord);

-- ---------- 第二本 ----------
WITH ins AS (
  INSERT INTO public.word_books (user_id, book_name, book_description, word_count, status, del_flag, create_time)
  VALUES (105, '考研高频词', '考研英语阅读常见词，偏学术语境', 10, '0', '0', '2026-10-21 10:00:00')
  RETURNING book_id
)
INSERT INTO public.words (book_id, word, phonetic, translation, example, sort_order, create_time)
SELECT book_id, v.word, v.phonetic, v.translation, v.example, v.ord, '2026-10-21 10:00:00'
FROM ins, (VALUES
  ('accumulate',   'əˈkjuːmjəleɪt',  'v. 积累；积聚',        'Data accumulated over several years.', 1),
  ('contradict',   'ˌkɒntrəˈdɪkt',   'v. 反驳；与…矛盾',     'The results contradict the earlier study.', 2),
  ('diminish',     'dɪˈmɪnɪʃ',       'v. 减少；削弱',        'The effect diminishes over time.', 3),
  ('elaborate',    'ɪˈlæbərət',      'adj. 精细的 v. 详述',  'Could you elaborate on that point?', 4),
  ('fundamental',  'ˌfʌndəˈmentl',   'adj. 根本的',          'This is a fundamental design flaw.', 5),
  ('hypothesis',   'haɪˈpɒθəsɪs',    'n. 假设',              'The hypothesis was tested in three trials.', 6),
  ('inevitable',   'ɪnˈevɪtəbl',     'adj. 不可避免的',      'Some technical debt is inevitable.', 7),
  ('magnitude',    'ˈmæɡnɪtjuːd',    'n. 量级；重要性',      'The error was small in magnitude.', 8),
  ('preliminary',  'prɪˈlɪmɪnəri',   'adj. 初步的',          'Preliminary results look promising.', 9),
  ('substantial',  'səbˈstænʃl',     'adj. 大量的；实质的',  'A substantial improvement in speed.', 10)
) AS v(word, phonetic, translation, example, ord);

-- 回填词数（以实际条数为准，别手写数字）
UPDATE public.word_books wb
SET word_count = (SELECT COUNT(*) FROM public.words w WHERE w.book_id = wb.book_id)
WHERE wb.book_name IN ('四级核心词', '考研高频词');
