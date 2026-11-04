-- 2026-11-04：监控/任务页面所需字典（操作类型 / 任务分组 / 任务状态）
INSERT INTO sys_dict_type (dict_id, dict_name, dict_type, status, create_time)
SELECT 8, '操作类型', 'sys_oper_type', '0', NOW()
WHERE NOT EXISTS (SELECT 1 FROM sys_dict_type WHERE dict_type = 'sys_oper_type');

INSERT INTO sys_dict_type (dict_id, dict_name, dict_type, status, create_time)
SELECT 9, '任务分组', 'sys_job_group', '0', NOW()
WHERE NOT EXISTS (SELECT 1 FROM sys_dict_type WHERE dict_type = 'sys_job_group');

INSERT INTO sys_dict_type (dict_id, dict_name, dict_type, status, create_time)
SELECT 10, '任务状态', 'sys_job_status', '0', NOW()
WHERE NOT EXISTS (SELECT 1 FROM sys_dict_type WHERE dict_type = 'sys_job_status');

INSERT INTO sys_dict_data (dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_time)
SELECT * FROM (VALUES
    (0, '其他', '0', 'sys_oper_type', '', 'info', 'N', '0', NOW()),
    (1, '新增', '1', 'sys_oper_type', '', 'primary', 'N', '0', NOW()),
    (2, '修改', '2', 'sys_oper_type', '', 'success', 'N', '0', NOW()),
    (3, '删除', '3', 'sys_oper_type', '', 'danger', 'N', '0', NOW()),
    (4, '授权', '4', 'sys_oper_type', '', 'primary', 'N', '0', NOW()),
    (5, '导出', '5', 'sys_oper_type', '', 'warning', 'N', '0', NOW()),
    (6, '导入', '6', 'sys_oper_type', '', 'warning', 'N', '0', NOW()),
    (7, '强退', '7', 'sys_oper_type', '', 'danger', 'N', '0', NOW()),
    (8, '清空', '8', 'sys_oper_type', '', 'danger', 'N', '0', NOW())
) AS v(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_time)
WHERE NOT EXISTS (
    SELECT 1 FROM sys_dict_data d WHERE d.dict_type = v.dict_type AND d.dict_value = v.dict_value
);

INSERT INTO sys_dict_data (dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_time)
SELECT * FROM (VALUES
    (0, '默认', 'DEFAULT', 'sys_job_group', '', 'primary', 'N', '0', NOW()),
    (1, '系统', 'SYSTEM', 'sys_job_group', '', 'info', 'N', '0', NOW())
) AS v(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_time)
WHERE NOT EXISTS (
    SELECT 1 FROM sys_dict_data d WHERE d.dict_type = v.dict_type AND d.dict_value = v.dict_value
);

INSERT INTO sys_dict_data (dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_time)
SELECT * FROM (VALUES
    (0, '正常', '0', 'sys_job_status', '', 'success', 'N', '0', NOW()),
    (1, '暂停', '1', 'sys_job_status', '', 'danger', 'N', '0', NOW())
) AS v(dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_time)
WHERE NOT EXISTS (
    SELECT 1 FROM sys_dict_data d WHERE d.dict_type = v.dict_type AND d.dict_value = v.dict_value
);
