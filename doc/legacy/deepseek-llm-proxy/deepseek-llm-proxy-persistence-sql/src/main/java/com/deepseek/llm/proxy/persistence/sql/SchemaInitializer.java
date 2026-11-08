package com.deepseek.llm.proxy.persistence.sql;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.PersistenceException;
import com.deepseek.llm.proxy.persistence.PersistenceConfig;
import com.deepseek.llm.proxy.persistence.TableConflictDetector;
import com.deepseek.llm.proxy.persistence.TableConflictException;
import com.deepseek.llm.proxy.persistence.TableDescriptor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Schema 初始化器
 * <p>
 * 根据 schema-init 策略执行：
 * <ul>
 *   <li>create-if-not-exists：表不存在则建表，存在则校验 schema</li>
 *   <li>validate：仅校验，不建表</li>
 *   <li>none：跳过检测</li>
 * </ul>
 * </p>
 */
public class SchemaInitializer {

    private static final Logger log = LoggerFactory.getLogger(SchemaInitializer.class);

    private final JdbcTemplate jdbcTemplate;
    private final Dialect dialect;
    private final DefaultSchemaScript schemaScript;
    private final SchemaCompatibilityChecker checker;
    private final SqlTableConflictDetector conflictDetector;
    private final PersistenceConfig.SqlConfig sqlConfig;

    public SchemaInitializer(JdbcTemplate jdbcTemplate, Dialect dialect,
                             DefaultSchemaScript schemaScript,
                             SchemaCompatibilityChecker checker,
                             SqlTableConflictDetector conflictDetector,
                             PersistenceConfig.SqlConfig sqlConfig) {
        this.jdbcTemplate = jdbcTemplate;
        this.dialect = dialect;
        this.schemaScript = schemaScript;
        this.checker = checker;
        this.conflictDetector = conflictDetector;
        this.sqlConfig = sqlConfig;
    }

    /**
     * 初始化会话表
     *
     * @param tableName 目标表名
     */
    public void initializeConversationTable(String tableName) throws PersistenceException {
        initializeTable(tableName, schemaScript.expectedConversationSchema(tableName),
                schemaScript.generateConversationDdl(tableName));
    }

    /**
     * 初始化记忆表
     */
    public void initializeMemoryTable(String tableName) throws PersistenceException {
        initializeTable(tableName, schemaScript.expectedMemorySchema(tableName),
                schemaScript.generateMemoryDdl(tableName));
    }

    private void initializeTable(String tableName, TableDescriptor expected, String createDdl)
            throws PersistenceException {
        String strategy = sqlConfig.getSchemaInit();
        if ("none".equalsIgnoreCase(strategy)) {
            log.info("schema-init=none，跳过表 {} 的检测", tableName);
            return;
        }

        boolean exists = checker.tableExists(tableName);

        if ("create-if-not-exists".equalsIgnoreCase(strategy)) {
            if (!exists) {
                log.info("表 {} 不存在，执行建表 SQL", tableName);
                try {
                    jdbcTemplate.execute(createDdl);
                } catch (DataAccessException e) {
                    throw new PersistenceException(ErrorCode.PERSISTENCE_INIT_FAILED,
                            "建表失败：" + e.getMessage() + "\n执行 SQL:\n" + createDdl, e);
                }
                return;
            }
            // 表存在，校验 schema
            validateAndResolve(tableName, expected);
            return;
        }

        if ("validate".equalsIgnoreCase(strategy)) {
            if (!exists) {
                throw new PersistenceException(ErrorCode.TABLE_NOT_FOUND,
                        "表 " + tableName + " 不存在。schema-init=validate 不允许自动建表。\n"
                                + "请手动执行以下 SQL 建表，或改用 schema-init=create-if-not-exists:\n"
                                + createDdl);
            }
            validateAndResolve(tableName, expected);
            return;
        }

        throw new PersistenceException(ErrorCode.FIELD_MAPPING_INVALID,
                "未知 schema-init 策略：" + strategy + "。支持：create-if-not-exists / validate / none");
    }

    private void validateAndResolve(String tableName, TableDescriptor expected) throws PersistenceException {
        TableConflictDetector.ConflictResult conflict = conflictDetector.detectConflict(tableName, expected);

        if (conflict.getSeverity() == TableConflictDetector.ConflictResult.Severity.INFO) {
            log.info("表 {} 结构校验通过", tableName);
            return;
        }

        // ERROR 级别冲突必须解决
        if (conflict.isBlocking()) {
            // 根据 conflictResolution 策略处理
            String policy = sqlConfig.getConflictResolution();
            if ("prompt".equalsIgnoreCase(policy)) {
                // 抛异常让开发者处理
                throw new TableConflictException(conflict, conflictDetector.listResolutionOptions(conflict));
            }
            if ("rename".equalsIgnoreCase(policy)) {
                log.warn("表 {} 存在冲突，应用 rename 策略：将改用 {} 前缀新表",
                        tableName, sqlConfig.getTablePrefix());
                return;
            }
            if ("use-existing".equalsIgnoreCase(policy)) {
                log.warn("表 {} 存在冲突，应用 use-existing 策略：强行复用（开发者保证语义一致）", tableName);
                return;
            }
            if ("fail".equalsIgnoreCase(policy)) {
                throw new TableConflictException(conflict, conflictDetector.listResolutionOptions(conflict));
            }
            throw new PersistenceException(ErrorCode.FIELD_MAPPING_INVALID,
                    "未知 conflict-resolution 策略：" + policy + "。支持：prompt / rename / use-existing / fail");
        }

        // WARN 级别，记录日志继续
        log.warn("表 {} 存在潜在冲突：{}", tableName, String.join(", ", conflict.getExtraColumns()));
    }
}
