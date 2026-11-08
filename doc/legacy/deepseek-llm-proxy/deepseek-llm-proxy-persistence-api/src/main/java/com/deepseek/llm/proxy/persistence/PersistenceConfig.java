package com.deepseek.llm.proxy.persistence;

import com.deepseek.llm.proxy.core.enums.PersistenceType;

import java.util.Map;

/**
 * 持久化配置
 */
public class PersistenceConfig {

    /** 存储类型 */
    private PersistenceType type = PersistenceType.NONE;

    /** Browser 存储配置 */
    private BrowserConfig browser = new BrowserConfig();

    /** SQL 存储配置 */
    private SqlConfig sql = new SqlConfig();

    public PersistenceType getType() { return type; }
    public void setType(PersistenceType type) { this.type = type; }
    public BrowserConfig getBrowser() { return browser; }
    public void setBrowser(BrowserConfig browser) { this.browser = browser; }
    public SqlConfig getSql() { return sql; }
    public void setSql(SqlConfig sql) { this.sql = sql; }

    /** Browser 存储配置 */
    public static class BrowserConfig {
        /** 存储键前缀（IndexedDB database name 前缀） */
        private String storageKeyPrefix = "ds-llm-proxy";
        /** 最大存储容量（MB） */
        private int maxSizeMb = 50;

        public String getStorageKeyPrefix() { return storageKeyPrefix; }
        public void setStorageKeyPrefix(String storageKeyPrefix) { this.storageKeyPrefix = storageKeyPrefix; }
        public int getMaxSizeMb() { return maxSizeMb; }
        public void setMaxSizeMb(int maxSizeMb) { this.maxSizeMb = maxSizeMb; }
    }

    /** SQL 存储配置 */
    public static class SqlConfig {
        /** 数据库方言：mysql / postgresql / hsqldb */
        private String dialect = "mysql";
        /** 表前缀，避免与业务表冲突 */
        private String tablePrefix = "ds_llm_proxy_";
        /** Schema 初始化策略：
         * <ul>
         *   <li>create-if-not-exists：不存在则建表（默认）</li>
         *   <li>validate：校验已有表，不匹配则报错</li>
         *   <li>none：跳过检测（开发者自管）</li>
         * </ul>
         */
        private String schemaInit = "create-if-not-exists";
        /** 冲突解决策略：
         * <ul>
         *   <li>prompt：抛异常让开发者选择（默认）</li>
         *   <li>rename：本 SDK 改用前缀新表</li>
         *   <li>use-existing：直接复用已有表</li>
         *   <li>fail：启动失败</li>
         * </ul>
         */
        private String conflictResolution = "prompt";
        /** 自定义会话表名（复用已有表，不使用默认前缀） */
        private String customConversationTable;
        /** 自定义记忆表名 */
        private String customMemoryTable;
        /** 字段映射配置 */
        private Map<String, Map<String, FieldMapping>> fieldMapping;

        public String getDialect() { return dialect; }
        public void setDialect(String dialect) { this.dialect = dialect; }
        public String getTablePrefix() { return tablePrefix; }
        public void setTablePrefix(String tablePrefix) { this.tablePrefix = tablePrefix; }
        public String getSchemaInit() { return schemaInit; }
        public void setSchemaInit(String schemaInit) { this.schemaInit = schemaInit; }
        public String getConflictResolution() { return conflictResolution; }
        public void setConflictResolution(String conflictResolution) { this.conflictResolution = conflictResolution; }
        public String getCustomConversationTable() { return customConversationTable; }
        public void setCustomConversationTable(String customConversationTable) { this.customConversationTable = customConversationTable; }
        public String getCustomMemoryTable() { return customMemoryTable; }
        public void setCustomMemoryTable(String customMemoryTable) { this.customMemoryTable = customMemoryTable; }
        public Map<String, Map<String, FieldMapping>> getFieldMapping() { return fieldMapping; }
        public void setFieldMapping(Map<String, Map<String, FieldMapping>> fieldMapping) { this.fieldMapping = fieldMapping; }
    }

    /** 字段映射（解决已有表字段不同的问题） */
    public static class FieldMapping {
        /** 映射到的目标列名 */
        private String column;
        /** 缺失字段策略：
         * <ul>
         *   <li>nullable：允许为 null</li>
         *   <li>skip：跳过此字段</li>
         *   <li>default:xxx：使用默认值 xxx</li>
         * </ul>
         */
        private String missingPolicy;
        /** 默认值（missingPolicy=default:xxx 时的 xxx） */
        private String defaultValue;

        public String getColumn() { return column; }
        public void setColumn(String column) { this.column = column; }
        public String getMissingPolicy() { return missingPolicy; }
        public void setMissingPolicy(String missingPolicy) { this.missingPolicy = missingPolicy; }
        public String getDefaultValue() { return defaultValue; }
        public void setDefaultValue(String defaultValue) { this.defaultValue = defaultValue; }
    }
}
