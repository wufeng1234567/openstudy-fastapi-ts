package com.deepseek.llm.proxy.starter;

import com.deepseek.llm.proxy.core.enums.PersistenceType;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.HashMap;
import java.util.Map;

/**
 * DeepSeek LLM Proxy 配置属性
 */
@ConfigurationProperties(prefix = "deepseek.llm-proxy")
public class LlmProxyProperties {

    /** 是否启用 */
    private boolean enabled = true;

    /** 后端服务地址 */
    private String serverUrl = "http://127.0.0.1:8086";

    /** 认证 token */
    private String token;

    /** API 版本 */
    private String apiVersion = "v1";

    /** 默认 Provider ID */
    private String defaultProvider = "deepseek-free";

    /** 全局默认超时（毫秒） */
    private long timeoutMs = 300000L;

    /** Agent 最大循环次数 */
    private int maxLoops = 10;

    /** 持久化配置 */
    private Persistence persistence = new Persistence();

    /** Provider 注册列表 */
    private Map<String, ProviderConfig> providers = new HashMap<>();

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public String getServerUrl() { return serverUrl; }
    public void setServerUrl(String serverUrl) { this.serverUrl = serverUrl; }
    public String getToken() { return token; }
    public void setToken(String token) { this.token = token; }
    public String getApiVersion() { return apiVersion; }
    public void setApiVersion(String apiVersion) { this.apiVersion = apiVersion; }
    public String getDefaultProvider() { return defaultProvider; }
    public void setDefaultProvider(String defaultProvider) { this.defaultProvider = defaultProvider; }
    public long getTimeoutMs() { return timeoutMs; }
    public void setTimeoutMs(long timeoutMs) { this.timeoutMs = timeoutMs; }
    public int getMaxLoops() { return maxLoops; }
    public void setMaxLoops(int maxLoops) { this.maxLoops = maxLoops; }
    public Persistence getPersistence() { return persistence; }
    public void setPersistence(Persistence persistence) { this.persistence = persistence; }
    public Map<String, ProviderConfig> getProviders() { return providers; }
    public void setProviders(Map<String, ProviderConfig> providers) { this.providers = providers; }

    /** 持久化配置 */
    public static class Persistence {
        /** 存储类型：none / browser / sql */
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
    }

    /** Browser 存储配置 */
    public static class BrowserConfig {
        private String storageKeyPrefix = "ds-llm-proxy";
        private int maxSizeMb = 50;

        public String getStorageKeyPrefix() { return storageKeyPrefix; }
        public void setStorageKeyPrefix(String storageKeyPrefix) { this.storageKeyPrefix = storageKeyPrefix; }
        public int getMaxSizeMb() { return maxSizeMb; }
        public void setMaxSizeMb(int maxSizeMb) { this.maxSizeMb = maxSizeMb; }
    }

    /** SQL 存储配置 */
    public static class SqlConfig {
        private String dialect = "mysql";
        private String tablePrefix = "ds_llm_proxy_";
        private String schemaInit = "create-if-not-exists";
        private String conflictResolution = "prompt";
        private String customConversationTable;
        private String customMemoryTable;
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

    /** 字段映射 */
    public static class FieldMapping {
        private String column;
        private String missingPolicy;
        private String defaultValue;

        public String getColumn() { return column; }
        public void setColumn(String column) { this.column = column; }
        public String getMissingPolicy() { return missingPolicy; }
        public void setMissingPolicy(String missingPolicy) { this.missingPolicy = missingPolicy; }
        public String getDefaultValue() { return defaultValue; }
        public void setDefaultValue(String defaultValue) { this.defaultValue = defaultValue; }
    }

    /** Provider 配置 */
    public static class ProviderConfig {
        private boolean enabled = true;
        private String providerClass;

        public boolean isEnabled() { return enabled; }
        public void setEnabled(boolean enabled) { this.enabled = enabled; }
        public String getProviderClass() { return providerClass; }
        public void setProviderClass(String providerClass) { this.providerClass = providerClass; }
    }
}
