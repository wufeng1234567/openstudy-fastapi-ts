-- 2026-11-03: 后台字典配置持久化（此前只存在进程内，重启丢失）
CREATE TABLE IF NOT EXISTS sys_dict_type (
    dict_id BIGSERIAL PRIMARY KEY,
    dict_name VARCHAR(100) NOT NULL,
    dict_type VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(1) DEFAULT '0',
    create_by VARCHAR(64) DEFAULT '',
    create_time TIMESTAMP DEFAULT now(),
    update_by VARCHAR(64) DEFAULT '',
    update_time TIMESTAMP,
    remark VARCHAR(500)
);

CREATE TABLE IF NOT EXISTS sys_dict_data (
    dict_code BIGSERIAL PRIMARY KEY,
    dict_sort INTEGER DEFAULT 0,
    dict_label VARCHAR(100) NOT NULL,
    dict_value VARCHAR(100) NOT NULL,
    dict_type VARCHAR(100) NOT NULL,
    css_class VARCHAR(100) DEFAULT '',
    list_class VARCHAR(100) DEFAULT '',
    is_default VARCHAR(1) DEFAULT 'N',
    status VARCHAR(1) DEFAULT '0',
    create_time TIMESTAMP DEFAULT now(),
    update_time TIMESTAMP,
    remark VARCHAR(500)
);
CREATE INDEX IF NOT EXISTS idx_sys_dict_data_type ON sys_dict_data (dict_type);
