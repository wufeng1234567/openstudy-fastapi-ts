package com.deepseek.llm.proxy.persistence;

import com.deepseek.llm.proxy.core.exception.PersistenceException;

import java.util.List;

/**
 * 表冲突检测器
 * <p>
 * 解决场景：开发者已有 agent_memory 表（或其他业务表），但功能/字段与 SDK 期望不同。
 * <ul>
 *   <li>场景 A：表完全不存在 → 报 TABLE_NOT_FOUND，提示创建 SQL</li>
 *   <li>场景 B：表存在但字段缺失/类型不匹配 → 报 TABLE_SCHEMA_MISMATCH，提示 ALTER SQL</li>
 *   <li>场景 C：表存在且字段匹配，但业务语义不同 → 报 TABLE_CONFLICT，列出可选解决方案</li>
 * </ul>
 * </p>
 */
public interface TableConflictDetector {

    /**
     * 检测目标表是否存在
     */
    boolean exists(String tableName) throws PersistenceException;

    /**
     * 检测表是否存在且结构冲突
     *
     * @param tableName 目标表名
     * @param expected  期望的表结构
     * @return 冲突检测结果
     */
    ConflictResult detectConflict(String tableName, TableDescriptor expected) throws PersistenceException;

    /**
     * 列出可选解决方案
     */
    List<ResolutionOption> listResolutionOptions(ConflictResult conflict);

    /**
     * 应用解决方案
     */
    void applyResolution(ConflictResult conflict, ResolutionOption option) throws PersistenceException;

    /**
     * 冲突检测结果
     */
    class ConflictResult {
        /** 表名 */
        private final String tableName;
        /** 表是否存在 */
        private final boolean tableExists;
        /** Schema 是否匹配 */
        private final boolean schemaMatch;
        /** 缺失的列 */
        private final List<String> missingColumns;
        /** 类型不匹配的列（每项格式：colName(期望 type / 实际 type)） */
        private final List<String> mismatchColumns;
        /** 多出的列（允许，不阻塞） */
        private final List<String> extraColumns;
        /** 建议的修复 SQL */
        private final List<String> repairSqls;
        /** 冲突严重级别：INFO / WARN / ERROR */
        private final Severity severity;

        public ConflictResult(String tableName, boolean tableExists, boolean schemaMatch,
                              List<String> missingColumns, List<String> mismatchColumns,
                              List<String> extraColumns, List<String> repairSqls, Severity severity) {
            this.tableName = tableName;
            this.tableExists = tableExists;
            this.schemaMatch = schemaMatch;
            this.missingColumns = missingColumns;
            this.mismatchColumns = mismatchColumns;
            this.extraColumns = extraColumns;
            this.repairSqls = repairSqls;
            this.severity = severity;
        }

        public String getTableName() { return tableName; }
        public boolean isTableExists() { return tableExists; }
        public boolean isSchemaMatch() { return schemaMatch; }
        public List<String> getMissingColumns() { return missingColumns; }
        public List<String> getMismatchColumns() { return mismatchColumns; }
        public List<String> getExtraColumns() { return extraColumns; }
        public List<String> getRepairSqls() { return repairSqls; }
        public Severity getSeverity() { return severity; }

        /** 是否需要阻塞启动 */
        public boolean isBlocking() {
            return severity == Severity.ERROR;
        }

        public enum Severity {
            /** 无冲突 */
            INFO,
            /** 有冲突但可自动修复或允许跳过 */
            WARN,
            /** 严重冲突，必须解决才能启动 */
            ERROR
        }
    }

    /**
     * 解决方案选项
     */
    class ResolutionOption {
        /** 选项 ID：use_existing / rename / create_new / skip / fail */
        private final String id;
        /** 描述 */
        private final String description;
        /** 执行的 SQL（如有） */
        private final String actionSql;
        /** 是否需要重启 SDK */
        private final boolean requiresRestart;

        public ResolutionOption(String id, String description, String actionSql, boolean requiresRestart) {
            this.id = id;
            this.description = description;
            this.actionSql = actionSql;
            this.requiresRestart = requiresRestart;
        }

        public String getId() { return id; }
        public String getDescription() { return description; }
        public String getActionSql() { return actionSql; }
        public boolean isRequiresRestart() { return requiresRestart; }
    }
}
