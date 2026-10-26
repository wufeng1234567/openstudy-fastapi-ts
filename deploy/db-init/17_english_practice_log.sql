-- ============================================================================
-- 英语练习记录（2026-10-26）
--
-- 解决什么：三个英语子页面（单词听写 / 阅读练习 / 拍照识词）原先都是**开环**的 ——
--   · 听写：关掉页面就忘了练到哪、哪些词错了；
--   · 阅读：做完题只看对错，错题不留存，也无法回顾；
--   · 识词：加完词没有"我加了多少"的记录。
-- 没有记录 = 没有"下次"，也谈不上任何复盘。
--
-- 这张表只做一件事：**把一次练习的结果落下来**，供：
--   ① 页面上的「上次练到哪」入口；
--   ② 智能体 `english_practice` 工具读出来做诊断（「我哪类词老错」）；
--   ③ 未来的复习计划（错词按遗忘曲线重排）。
--
-- 设计取舍：
--   · 用 `detail` JSONB 存逐题明细，不建第二张"逐题表"——
--     明细只被整体读取（渲染结果页 / 算正确率），从不按单题查询，
--     拆表只会让每次练习要写 N 行。
--   · `mode` 区分练习类型（dictation=听写 / reading=阅读 / ocr=识词），
--     一个表装三类，因为它们的字段形状一致（都对/错/得分）。
--   · 软删 `del_flag` 与项目其它表一致。
-- ============================================================================

CREATE TABLE IF NOT EXISTS english_practice_log (
    id              BIGSERIAL PRIMARY KEY,
    --: 归属用户（与词书的 user_id 同一口径）
    user_id         BIGINT       NOT NULL,
    --: dictation / reading / ocr
    mode            VARCHAR(32)  NOT NULL,
    --: 关联词书（阅读/识词可为空）
    book_id         BIGINT,
    --: 词书名 / 阅读主题，用于列表展示（避免每次都 join）
    title           VARCHAR(255),
    --: 题量 / 总词数
    total           INT          NOT NULL DEFAULT 0,
    --: 答对 / 写对的数量
    correct         INT          NOT NULL DEFAULT 0,
    --: 正确率（0~100，四舍五入到整数，避免前端再算一遍口径不一致）
    accuracy        INT          NOT NULL DEFAULT 0,
    --: 用时（秒）
    duration        INT          NOT NULL DEFAULT 0,
    --: 逐题明细：[{"word":"abandon","input":"abandan","ok":false}, ...]
    detail          JSONB        NOT NULL DEFAULT '[]'::jsonb,
    del_flag        CHAR(1)      NOT NULL DEFAULT '0',
    create_time     TIMESTAMP    NOT NULL DEFAULT now()
);

--: 列表查询：某人的最近练习（页面上「上次练习」入口）
CREATE INDEX IF NOT EXISTS idx_english_practice_user_time
    ON english_practice_log (user_id, create_time DESC)
    WHERE del_flag = '0';

--: 按模式统计：智能体诊断「我阅读练了几次、正确率多少」
CREATE INDEX IF NOT EXISTS idx_english_practice_user_mode
    ON english_practice_log (user_id, mode)
    WHERE del_flag = '0';

COMMENT ON TABLE english_practice_log IS '英语练习记录（听写/阅读/识词），供页面回顾与智能体诊断';
COMMENT ON COLUMN english_practice_log.mode IS 'dictation=单词听写 / reading=阅读练习 / ocr=拍照识词';
COMMENT ON COLUMN english_practice_log.detail IS '逐题明细 JSON 数组，元素形如 {word, input, ok}';
