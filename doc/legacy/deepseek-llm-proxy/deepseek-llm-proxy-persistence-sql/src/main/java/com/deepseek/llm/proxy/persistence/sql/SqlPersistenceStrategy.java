package com.deepseek.llm.proxy.persistence.sql;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.enums.PersistenceType;
import com.deepseek.llm.proxy.core.exception.PersistenceException;
import com.deepseek.llm.proxy.core.model.Conversation;
import com.deepseek.llm.proxy.core.model.MemoryRecord;
import com.deepseek.llm.proxy.persistence.ConversationRepository;
import com.deepseek.llm.proxy.persistence.MemoryRepository;
import com.deepseek.llm.proxy.persistence.PersistenceConfig;
import com.deepseek.llm.proxy.persistence.PersistenceStrategy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;

import java.util.List;
import java.util.Optional;

/**
 * SQL 持久化策略实现
 * <p>
 * 基于 JdbcTemplate 实现，支持 MySQL/PostgreSQL/HSQLDB/SQLite/Oracle 多方言。
 * 启动时执行 SchemaInitializer 检测表冲突并自动处理。
 * </p>
 */
public class SqlPersistenceStrategy implements PersistenceStrategy {

    private static final Logger log = LoggerFactory.getLogger(SqlPersistenceStrategy.class);

    private final JdbcTemplate jdbcTemplate;
    private final PersistenceConfig.SqlConfig sqlConfig;
    private final Dialect dialect;
    private final DefaultSchemaScript schemaScript;
    private final SchemaCompatibilityChecker checker;
    private final SqlTableConflictDetector conflictDetector;
    private final SchemaInitializer schemaInitializer;

    private String conversationTableName;
    private String memoryTableName;
    private ConversationRepository conversationRepository;
    private MemoryRepository memoryRepository;
    private boolean initialized = false;

    public SqlPersistenceStrategy(JdbcTemplate jdbcTemplate, PersistenceConfig.SqlConfig sqlConfig) {
        this.jdbcTemplate = jdbcTemplate;
        this.sqlConfig = sqlConfig;
        this.dialect = Dialect.fromString(sqlConfig.getDialect());
        this.schemaScript = new DefaultSchemaScript(dialect);
        this.checker = new SchemaCompatibilityChecker(jdbcTemplate, dialect);
        this.conflictDetector = new SqlTableConflictDetector(jdbcTemplate, dialect, checker, sqlConfig);
        this.schemaInitializer = new SchemaInitializer(jdbcTemplate, dialect, schemaScript,
                checker, conflictDetector, sqlConfig);
    }

    @Override
    public PersistenceType getType() {
        return PersistenceType.SQL;
    }

    @Override
    public void initialize() throws PersistenceException {
        // 解析表名
        conversationTableName = resolveTableName(
                sqlConfig.getCustomConversationTable(), "conversation");
        memoryTableName = resolveTableName(
                sqlConfig.getCustomMemoryTable(), "memory");

        log.info("初始化 SQL 持久化：方言={}, 会话表={}, 记忆表={}, schema-init={}, conflict-resolution={}",
                dialect, conversationTableName, memoryTableName,
                sqlConfig.getSchemaInit(), sqlConfig.getConflictResolution());

        // 初始化两张表（含冲突检测）
        schemaInitializer.initializeConversationTable(conversationTableName);
        schemaInitializer.initializeMemoryTable(memoryTableName);

        // 创建 Repository
        conversationRepository = new SqlConversationRepository(jdbcTemplate, conversationTableName);
        memoryRepository = new SqlMemoryRepository(jdbcTemplate, memoryTableName);

        initialized = true;
        log.info("SQL 持久化初始化完成");
    }

    /** 解析表名：优先用自定义表名，否则用 前缀 + 默认名 */
    private String resolveTableName(String customName, String defaultSuffix) {
        if (customName != null && !customName.isEmpty()) {
            return customName;
        }
        return sqlConfig.getTablePrefix() + defaultSuffix;
    }

    @Override
    public boolean isHealthy() {
        if (!initialized) return false;
        try {
            return checker.tableExists(conversationTableName)
                    && checker.tableExists(memoryTableName);
        } catch (Exception e) {
            log.warn("SQL 持久化健康检查失败：{}", e.getMessage());
            return false;
        }
    }

    @Override
    public void saveConversation(Conversation conversation) throws PersistenceException {
        ensureInitialized();
        conversationRepository.save(conversation);
    }

    @Override
    public Optional<Conversation> loadConversation(String sessionId) throws PersistenceException {
        ensureInitialized();
        Conversation c = conversationRepository.findById(sessionId);
        return Optional.ofNullable(c);
    }

    @Override
    public List<Conversation> listConversations(String userId, int limit, int offset)
            throws PersistenceException {
        ensureInitialized();
        return conversationRepository.findByUserId(userId, limit, offset);
    }

    @Override
    public boolean deleteConversation(String sessionId) throws PersistenceException {
        ensureInitialized();
        return conversationRepository.deleteById(sessionId);
    }

    @Override
    public void saveMemory(MemoryRecord memory) throws PersistenceException {
        ensureInitialized();
        memoryRepository.save(memory);
    }

    @Override
    public Optional<MemoryRecord> loadMemory(String userId, String providerId) throws PersistenceException {
        ensureInitialized();
        return memoryRepository.findByUserIdAndProvider(userId, providerId);
    }

    @Override
    public boolean clearMemory(String userId, String providerId) throws PersistenceException {
        ensureInitialized();
        return memoryRepository.clear(userId, providerId);
    }

    @Override
    public void destroy() throws PersistenceException {
        if (!initialized) {
            return;
        }
        try {
            jdbcTemplate.execute("DROP TABLE IF EXISTS " + conversationTableName);
            jdbcTemplate.execute("DROP TABLE IF EXISTS " + memoryTableName);
            log.warn("已删除表 {} 和 {}", conversationTableName, memoryTableName);
            initialized = false;
        } catch (Exception e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_DESTROY_FAILED,
                    "销毁 SQL 存储失败：" + e.getMessage(), e);
        }
    }

    private void ensureInitialized() throws PersistenceException {
        if (!initialized) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_NOT_CONFIGURED,
                    "SQL 持久化未初始化，请先调用 initialize()");
        }
    }
}
