-- 2026-11-03: 题库练习会话/成绩快照（服务端权威判分）
CREATE TABLE IF NOT EXISTS user_practice_session (
    id BIGSERIAL PRIMARY KEY,
    session_key VARCHAR(64) NOT NULL UNIQUE,
    user_id BIGINT NOT NULL,
    bank_id BIGINT NOT NULL,
    module_type VARCHAR(20) NOT NULL DEFAULT 'sequential',
    question_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    answers JSONB NOT NULL DEFAULT '{}'::jsonb,
    score_config JSONB,
    status VARCHAR(16) NOT NULL DEFAULT 'ongoing',
    total_count INTEGER NOT NULL DEFAULT 0,
    answered_count INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    wrong_count INTEGER NOT NULL DEFAULT 0,
    pending_count INTEGER NOT NULL DEFAULT 0,
    score NUMERIC(8,2) NOT NULL DEFAULT 0,
    total_score NUMERIC(8,2) NOT NULL DEFAULT 0,
    duration_sec INTEGER,
    create_time TIMESTAMP NOT NULL DEFAULT now(),
    submit_time TIMESTAMP,
    update_time TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_practice_session_user_time
    ON user_practice_session (user_id, create_time);
