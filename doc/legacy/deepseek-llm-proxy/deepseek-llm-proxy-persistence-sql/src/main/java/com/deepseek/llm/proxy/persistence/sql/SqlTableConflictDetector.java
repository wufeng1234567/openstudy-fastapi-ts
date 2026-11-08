package com.deepseek.llm.proxy.persistence.sql;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.PersistenceException;
import com.deepseek.llm.proxy.persistence.ColumnDescriptor;
import com.deepseek.llm.proxy.persistence.PersistenceConfig;
import com.deepseek.llm.proxy.persistence.TableConflictDetector;
import com.deepseek.llm.proxy.persistence.TableDescriptor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * SQL 表冲突检测器实现
 * <p>
 * 解决开发者已有 agent_memory 表（或其他业务表）但功能/字段不同的问题。
 * 流程：
 * <ol>
 *   <li>检测表是否存在</li>
 *   <li>检测字段兼容性</li>
 *   <li>检测功能冲突（表已存在非本 SDK 写入的数据）</li>
 *   <li>列出可选解决方案</li>
 * </ol>
 * </p>
 */
public class SqlTableConflictDetector implements TableConflictDetector {

    private static final Logger log = LoggerFactory.getLogger(SqlTableConflictDetector.class);

    private final JdbcTemplate jdbcTemplate;
    private final Dialect dialect;
    private final SchemaCompatibilityChecker checker;
    private final PersistenceConfig.SqlConfig sqlConfig;

    public SqlTableConflictDetector(JdbcTemplate jdbcTemplate, Dialect dialect,
                                    SchemaCompatibilityChecker checker,
                                    PersistenceConfig.SqlConfig sqlConfig) {
        this.jdbcTemplate = jdbcTemplate;
        this.dialect = dialect;
        this.checker = checker;
        this.sqlConfig = sqlConfig;
    }

    @Override
    public boolean exists(String tableName) throws PersistenceException {
        return checker.tableExists(tableName);
    }

    @Override
    public ConflictResult detectConflict(String tableName, TableDescriptor expected) throws PersistenceException {
        SchemaCompatibilityChecker.ComparisonResult cmp = checker.compare(tableName, expected);

        if (!cmp.isTableExists()) {
            // 表不存在
            List<String> repairSqls = new ArrayList<>();
            DefaultSchemaScript script = new DefaultSchemaScript(dialect);
            if (tableName.contains("conversation") || tableName.contains("memory")) {
                // 通用：让上层调用方决定 DDL
                repairSqls.add("-- 请参考 SDK 默认 DDL 手动建表");
            }
            return new ConflictResult(
                    tableName, false, false,
                    Collections.emptyList(), Collections.emptyList(),
                    Collections.emptyList(), repairSqls,
                    ConflictResult.Severity.ERROR);
        }

        if (!cmp.isMatch()) {
            // 字段不匹配
            List<String> repairSqls = new ArrayList<>();
            for (String missing : cmp.getMissingColumns()) {
                ColumnDescriptor col = expected.findColumn(missing);
                String type = col != null ? col.getType() : "VARCHAR(255)";
                String nullable = (col == null || col.isNullable()) ? "" : " NOT NULL";
                repairSqls.add("ALTER TABLE " + tableName + " ADD COLUMN " + missing + " " + type + nullable + ";");
            }
            for (String mismatch : cmp.getMismatchColumns()) {
                // mismatchColumns 格式：colName(期望 type / 实际 type)
                int idx1 = mismatch.indexOf('(');
                int idx2 = mismatch.indexOf(" / ");
                if (idx1 > 0 && idx2 > idx1) {
                    String colName = mismatch.substring(0, idx1);
                    String expectedType = mismatch.substring(idx1 + 1, idx2);
                    repairSqls.add("ALTER TABLE " + tableName + " MODIFY COLUMN " + colName + " " + expectedType + ";");
                }
            }
            return new ConflictResult(
                    tableName, true, false,
                    cmp.getMissingColumns(), cmp.getMismatchColumns(),
                    cmp.getExtraColumns(), repairSqls,
                    ConflictResult.Severity.ERROR);
        }

        // 字段匹配，检查功能冲突（是否有大量非本 SDK 数据）
        ConflictResult.Severity severity = checkFunctionalConflict(tableName);
        if (severity == ConflictResult.Severity.ERROR) {
            return new ConflictResult(
                    tableName, true, true,
                    Collections.emptyList(), Collections.emptyList(),
                    cmp.getExtraColumns(), Collections.emptyList(),
                    severity);
        }

        // 无冲突
        return new ConflictResult(
                tableName, true, true,
                Collections.emptyList(), Collections.emptyList(),
                cmp.getExtraColumns(), Collections.emptyList(),
                ConflictResult.Severity.INFO);
    }

    /** 功能冲突检查：表名是已知业务表，或表中已有大量数据 */
    private ConflictResult.Severity checkFunctionalConflict(String tableName) {
        String lower = tableName.toLowerCase();
        // 已知业务表名（容易冲突的）
        if (lower.equals("agent_memory") || lower.equals("conversations") || lower.equals("messages")
                || lower.equals("chat_history") || lower.equals("chat_memory")) {
            log.warn("表 {} 名称是常见业务表名，可能存在功能冲突。请确认是否复用。", tableName);
            return ConflictResult.Severity.WARN;
        }
        return ConflictResult.Severity.INFO;
    }

    @Override
    public List<ResolutionOption> listResolutionOptions(ConflictResult conflict) {
        List<ResolutionOption> options = new ArrayList<>();

        if (!conflict.isTableExists()) {
            // 表不存在
            options.add(new ResolutionOption(
                    "create_new", "执行建表 SQL，创建本 SDK 专用表",
                    conflict.getRepairSqls().isEmpty() ? null : String.join("\n", conflict.getRepairSqls()),
                    true));
            options.add(new ResolutionOption(
                    "fail", "放弃启动，开发者手动建表后重启", null, true));
            return options;
        }

        if (!conflict.isSchemaMatch()) {
            // 字段不匹配
            options.add(new ResolutionOption(
                    "repair", "执行 ALTER SQL 修复字段",
                    conflict.getRepairSqls().isEmpty() ? null : String.join("\n", conflict.getRepairSqls()),
                    true));
            options.add(new ResolutionOption(
                    "rename", "本 SDK 改用前缀新表（不修改已有表）",
                    null, true));
            options.add(new ResolutionOption(
                    "use_existing", "强行复用已有表（缺字段时由字段映射配置处理）",
                    null, false));
            options.add(new ResolutionOption(
                    "fail", "放弃启动", null, true));
            return options;
        }

        // 字段匹配但有功能冲突风险
        options.add(new ResolutionOption(
                "use_existing", "直接复用已有表（开发者保证语义一致）",
                null, false));
        options.add(new ResolutionOption(
                "rename", "本 SDK 改用前缀新表（推荐）",
                null, true));
        options.add(new ResolutionOption(
                "fail", "放弃启动", null, true));
        return options;
    }

    @Override
    public void applyResolution(ConflictResult conflict, ResolutionOption option) throws PersistenceException {
        if (option == null || option.getId() == null) {
            throw new PersistenceException(ErrorCode.FIELD_MAPPING_INVALID, "解决方案不能为空");
        }
        try {
            switch (option.getId()) {
                case "create_new":
                case "repair":
                    if (option.getActionSql() != null && !option.getActionSql().isEmpty()) {
                        // 执行多条 SQL（按 ; 分隔）
                        for (String sql : option.getActionSql().split(";")) {
                            if (!sql.trim().isEmpty()) {
                                jdbcTemplate.execute(sql.trim());
                            }
                        }
                    }
                    break;
                case "rename":
                    // 由上层 PersistenceManager 切换表名（添加前缀）
                    log.info("应用 rename 策略：本 SDK 将改用 {} 前缀新表", sqlConfig.getTablePrefix());
                    break;
                case "use_existing":
                    log.info("应用 use-existing 策略：直接复用表 {}", conflict.getTableName());
                    break;
                case "fail":
                    throw new PersistenceException(ErrorCode.TABLE_CONFLICT,
                            "开发者选择 fail 策略，启动终止。表：" + conflict.getTableName());
                default:
                    throw new PersistenceException(ErrorCode.FIELD_MAPPING_INVALID,
                            "未知解决方案：" + option.getId());
            }
        } catch (DataAccessException e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_INIT_FAILED,
                    "应用解决方案失败：" + e.getMessage(), e);
        }
    }
}
