-- 2026-11-04：后台监控补齐操作日志 / 登录日志 / 定时任务 / 调度日志
-- 前端页面原本就存在（views/monitor/*），此前因后端无表而隐藏菜单。

CREATE TABLE IF NOT EXISTS sys_oper_log (
    oper_id        BIGSERIAL PRIMARY KEY,
    title          VARCHAR(50)  DEFAULT '',
    business_type  INTEGER      DEFAULT 0,
    method         VARCHAR(255) DEFAULT '',
    request_method VARCHAR(10)  DEFAULT '',
    operator_type  INTEGER      DEFAULT 0,
    oper_name      VARCHAR(50)  DEFAULT '',
    dept_name      VARCHAR(50)  DEFAULT '',
    oper_url       VARCHAR(255) DEFAULT '',
    oper_ip        VARCHAR(128) DEFAULT '',
    oper_location  VARCHAR(255) DEFAULT '',
    oper_param     TEXT,
    json_result    TEXT,
    status         INTEGER      DEFAULT 0,
    error_msg      TEXT,
    oper_time      TIMESTAMP    DEFAULT NOW(),
    cost_time      BIGINT       DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sys_oper_log_time ON sys_oper_log (oper_time);
CREATE INDEX IF NOT EXISTS idx_sys_oper_log_name ON sys_oper_log (oper_name);

CREATE TABLE IF NOT EXISTS sys_logininfor (
    info_id        BIGSERIAL PRIMARY KEY,
    user_name      VARCHAR(50)  DEFAULT '',
    ipaddr         VARCHAR(128) DEFAULT '',
    login_location VARCHAR(255) DEFAULT '',
    browser        VARCHAR(50)  DEFAULT '',
    os             VARCHAR(50)  DEFAULT '',
    status         INTEGER      DEFAULT 0,
    msg            VARCHAR(255) DEFAULT '',
    login_time     TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sys_logininfor_time ON sys_logininfor (login_time);
CREATE INDEX IF NOT EXISTS idx_sys_logininfor_name ON sys_logininfor (user_name);

CREATE TABLE IF NOT EXISTS sys_job (
    job_id          BIGSERIAL PRIMARY KEY,
    job_name        VARCHAR(64)  NOT NULL UNIQUE,
    job_group       VARCHAR(64)  DEFAULT 'DEFAULT',
    invoke_target   VARCHAR(255) NOT NULL,
    cron_expression VARCHAR(255) NOT NULL,
    misfire_policy  VARCHAR(1)   DEFAULT '1',
    concurrent      VARCHAR(1)   DEFAULT '1',
    status          VARCHAR(1)   DEFAULT '0',
    remark          VARCHAR(500) DEFAULT '',
    create_time     TIMESTAMP    DEFAULT NOW(),
    update_time     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sys_job_status ON sys_job (status);

CREATE TABLE IF NOT EXISTS sys_job_log (
    job_log_id    BIGSERIAL PRIMARY KEY,
    job_name      VARCHAR(64)  DEFAULT '',
    job_group     VARCHAR(64)  DEFAULT '',
    invoke_target VARCHAR(255) DEFAULT '',
    job_message   VARCHAR(500) DEFAULT '',
    status        INTEGER      DEFAULT 0,
    exception_info TEXT,
    create_time   TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sys_job_log_time ON sys_job_log (create_time);
CREATE INDEX IF NOT EXISTS idx_sys_job_log_name ON sys_job_log (job_name);

-- 预置任务：都有真实实现（见 app/services/job_scheduler.py 的 _TASKS 白名单）
INSERT INTO sys_job (job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, remark, create_time)
SELECT '练习会话过期清理', 'DEFAULT', 'practiceSessionCleanup', '0 */10 * * * ?', '1', '1', '0', '把超过 2 小时未交卷的练习会话标记为 expired', NOW()
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE job_name = '练习会话过期清理');

INSERT INTO sys_job (job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, remark, create_time)
SELECT '文档处理中断回收', 'SYSTEM', 'documentPipelineRecovery', '0 */30 * * * ?', '1', '1', '0', '回收卡在解析中的 RAG 文档，避免长期占用处理队列', NOW()
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE job_name = '文档处理中断回收');

INSERT INTO sys_job (job_name, job_group, invoke_target, cron_expression, misfire_policy, concurrent, status, remark, create_time)
SELECT '历史日志清理', 'SYSTEM', 'logCleanup', '0 0 3 * * ?', '1', '1', '0', '清理 90 天前操作/登录日志、30 天前调度日志', NOW()
WHERE NOT EXISTS (SELECT 1 FROM sys_job WHERE job_name = '历史日志清理');

-- 恢复后台菜单显示（visible: 0=显示，1=隐藏）
UPDATE sys_menu SET visible = '0' WHERE menu_id IN (108, 110, 500, 501);
