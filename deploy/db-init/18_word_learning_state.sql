-- ============================================================================
-- 单词记忆状态表（2026-10-26）
--
-- ## 解决什么
--
-- 在此之前，`words` 表是一份**静态清单**：它只知道"这个库里有 42 个词"，
-- 不知道"哪几个我已经记住了""今天该复习哪几个"。
--
-- 后果是用户每次打开听写页，面对的永远是同一批词、同一个顺序 ——
-- 练完关掉，下次还得从头翻。文档里写了很久的
-- 「未来的复习计划（错词按遗忘曲线重排）」一直没落地，就是缺这张表。
--
-- ## 用什么算法
--
-- **SM-2 简化版**（SuperMemo 2，Anki 用的就是它的变体）。
--
-- 选它而不是"艾宾浩斯固定表格"（1天/2天/4天/7天/15天）的理由：
--   · 固定表格不区分单词难度 —— 一个早就认识的词和一个反复错的词
--     走同一条曲线，等于没做个性化；
--   · SM-2 用 `ease`（难度系数）给每个词单独记难度，
--     答错就降（下次来得更早）、答对就升（间隔拉更长）；
--   · 它只需要 4 个字段就能算，实现量小、可解释、可复现 ——
--     用户问"为什么今天让我背这 20 个"，能给出确切答案。
--
-- 复习间隔公式：
--     首次答对       → 1 天
--     第二次答对     → 3 天
--     之后每次答对   → 上次间隔 × ease（默认 2.5，答错时降到最低 1.3）
--     答错           → 回到 1 天，ease 降低 0.2，lapses +1
--
-- ## 设计取舍
--
-- · **一个词一行**，主键 (user_id, word_id)：同一个词在不同用户下
--   进度必须独立；用 `word_id` 而不是 `word` 文本，因为改名/同形不同义
--   都靠 id 区分。
-- · 不存 `review_count` 以外的历史明细 —— 复习历史已经在
--   `english_practice_log.detail` 里了，这里只存**当前状态**（快照），
--   避免每次复习都往这张表追加导致无限膨胀。
-- · `stage` 到 8 视为"已掌握"，不再进入日常复习，只在统计里体现。
-- ============================================================================

CREATE TABLE IF NOT EXISTS word_learning_state (
    --: 归属用户
    user_id         BIGINT      NOT NULL,
    --: 对应 words.word_id
    word_id         BIGINT      NOT NULL,

    --: 复习阶段：0=新词（没练过），1~7=复习中，8=已掌握
    stage           SMALLINT    NOT NULL DEFAULT 0,

    --: SM-2 难度系数：答对升、答错降。范围 [1.3, 3.0]，默认 2.5
    ease            REAL        NOT NULL DEFAULT 2.5,

    --: 当前复习间隔（天）。新词为 0
    interval_days   INT         NOT NULL DEFAULT 0,

    --: 下次该复习的日期（只到天，便于按天聚合查询）
    due_date        DATE,

    --: 累计答对次数
    right_count     INT         NOT NULL DEFAULT 0,
    --: 累计答错次数
    wrong_count     INT         NOT NULL DEFAULT 0,
    --: 遗忘次数（曾经记住后来答错的次数），用于衡量"这个词到底难不难"
    lapses          INT         NOT NULL DEFAULT 0,

    --: 首次练习时间
    first_seen_at   TIMESTAMP,
    --: 最近一次练习时间
    last_review_at  TIMESTAMP,

    PRIMARY KEY (user_id, word_id)
);

-- 查"今天该复习哪些词"：按 (用户, 到期日) 过滤，是最热的查询路径
CREATE INDEX IF NOT EXISTS idx_wls_due
    ON word_learning_state (user_id, due_date)
    WHERE due_date IS NOT NULL;

-- 查"这个词库的掌握情况"：需要 join words，故按 word_id 建
CREATE INDEX IF NOT EXISTS idx_wls_word
    ON word_learning_state (word_id);

-- 统计"已掌握多少 / 学习中多少"
CREATE INDEX IF NOT EXISTS idx_wls_stage
    ON word_learning_state (user_id, stage);

COMMENT ON TABLE  word_learning_state IS '单词记忆状态（SM-2 简化的间隔重复）';
COMMENT ON COLUMN word_learning_state.stage IS '0=新词 1~7=复习中 8=已掌握';
COMMENT ON COLUMN word_learning_state.ease IS 'SM-2 难度系数 [1.3, 3.0]';
COMMENT ON COLUMN word_learning_state.lapses IS '遗忘次数（记住后又答错）';
