package com.deepseek.llm.proxy.persistence.browser;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.enums.PersistenceType;
import com.deepseek.llm.proxy.core.exception.PersistenceException;
import com.deepseek.llm.proxy.core.model.Conversation;
import com.deepseek.llm.proxy.core.model.MemoryRecord;
import com.deepseek.llm.proxy.persistence.PersistenceConfig;
import com.deepseek.llm.proxy.persistence.PersistenceStrategy;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * 浏览器本地化存储策略实现
 * <p>
 * 通过 {@link BrowserStorageAdapter} 把存储任务下发到浏览器扩展执行，
 * 实际数据存在扩展的 IndexedDB 中。
 * </p>
 * <p>
 * 适用场景：单机、轻量、无需跨设备同步。
 * 优点：零数据库配置，开箱即用。
 * 缺点：容量有限（默认 50MB），不支持跨设备。
 * </p>
 */
public class BrowserPersistenceStrategy implements PersistenceStrategy {

    private static final Logger log = LoggerFactory.getLogger(BrowserPersistenceStrategy.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final BrowserStorageAdapter adapter;
    private final PersistenceConfig.BrowserConfig config;
    private boolean initialized = false;

    public BrowserPersistenceStrategy(BrowserStorageAdapter adapter,
                                      PersistenceConfig.BrowserConfig config) {
        this.adapter = adapter;
        this.config = config;
    }

    @Override
    public PersistenceType getType() {
        return PersistenceType.BROWSER;
    }

    @Override
    public void initialize() throws PersistenceException {
        if (!adapter.isExtensionOnline()) {
            throw new PersistenceException(ErrorCode.BROWSER_STORAGE_UNAVAILABLE,
                    "浏览器扩展未连接，无法初始化 IndexedDB 存储。"
                            + "请确保浏览器扩展已安装并启用。");
        }

        BrowserStorageTask task = new BrowserStorageTask(
                UUID.randomUUID().toString(),
                "init",
                "{\"storageKeyPrefix\":\"" + config.getStorageKeyPrefix()
                        + "\",\"maxSizeMb\":" + config.getMaxSizeMb() + "}");

        BrowserStorageResult result = adapter.dispatch(task);
        if (!result.isSuccess()) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_INIT_FAILED,
                    "IndexedDB 初始化失败：" + result.getErrorMessage());
        }
        initialized = true;
        log.info("浏览器 IndexedDB 存储初始化完成（prefix={}, maxSize={}MB）",
                config.getStorageKeyPrefix(), config.getMaxSizeMb());
    }

    @Override
    public boolean isHealthy() {
        if (!initialized) return false;
        try {
            BrowserStorageTask task = new BrowserStorageTask(
                    UUID.randomUUID().toString(), "health", "{}");
            BrowserStorageResult r = adapter.dispatch(task);
            return r.isSuccess();
        } catch (Exception e) {
            return false;
        }
    }

    @Override
    public void saveConversation(Conversation conversation) throws PersistenceException {
        ensureInitialized();
        try {
            String json = MAPPER.writeValueAsString(conversation);
            dispatch("save-conversation", json);
        } catch (Exception e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_WRITE_FAILED,
                    "保存会话到浏览器失败：" + e.getMessage(), e);
        }
    }

    @Override
    public Optional<Conversation> loadConversation(String sessionId) throws PersistenceException {
        ensureInitialized();
        try {
            BrowserStorageResult r = dispatch("load-conversation",
                    "{\"sessionId\":\"" + sessionId + "\"}");
            if (!r.isSuccess() || r.getDataJson() == null) {
                return Optional.empty();
            }
            Conversation c = MAPPER.readValue(r.getDataJson(), Conversation.class);
            return Optional.of(c);
        } catch (Exception e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_READ_FAILED,
                    "从浏览器加载会话失败：" + e.getMessage(), e);
        }
    }

    @Override
    public List<Conversation> listConversations(String userId, int limit, int offset)
            throws PersistenceException {
        ensureInitialized();
        try {
            BrowserStorageResult r = dispatch("list-conversations",
                    "{\"userId\":\"" + userId + "\",\"limit\":" + limit + ",\"offset\":" + offset + "}");
            if (!r.isSuccess() || r.getDataJson() == null) {
                return Collections.emptyList();
            }
            return MAPPER.readValue(r.getDataJson(), new TypeReference<List<Conversation>>() {});
        } catch (Exception e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_READ_FAILED,
                    "从浏览器列出会话失败：" + e.getMessage(), e);
        }
    }

    @Override
    public boolean deleteConversation(String sessionId) throws PersistenceException {
        ensureInitialized();
        BrowserStorageResult r = dispatch("delete-conversation",
                "{\"sessionId\":\"" + sessionId + "\"}");
        return r.isSuccess();
    }

    @Override
    public void saveMemory(MemoryRecord memory) throws PersistenceException {
        ensureInitialized();
        try {
            String json = MAPPER.writeValueAsString(memory);
            dispatch("save-memory", json);
        } catch (Exception e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_WRITE_FAILED,
                    "保存记忆到浏览器失败：" + e.getMessage(), e);
        }
    }

    @Override
    public Optional<MemoryRecord> loadMemory(String userId, String providerId) throws PersistenceException {
        ensureInitialized();
        try {
            BrowserStorageResult r = dispatch("load-memory",
                    "{\"userId\":\"" + userId + "\",\"providerId\":\"" + providerId + "\"}");
            if (!r.isSuccess() || r.getDataJson() == null) {
                return Optional.empty();
            }
            MemoryRecord m = MAPPER.readValue(r.getDataJson(), MemoryRecord.class);
            return Optional.of(m);
        } catch (Exception e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_READ_FAILED,
                    "从浏览器加载记忆失败：" + e.getMessage(), e);
        }
    }

    @Override
    public boolean clearMemory(String userId, String providerId) throws PersistenceException {
        ensureInitialized();
        BrowserStorageResult r = dispatch("clear-memory",
                "{\"userId\":\"" + userId + "\",\"providerId\":\"" + providerId + "\"}");
        return r.isSuccess();
    }

    @Override
    public void destroy() throws PersistenceException {
        if (!initialized) return;
        try {
            dispatch("destroy", "{}");
            initialized = false;
            log.warn("已销毁浏览器 IndexedDB 存储（prefix={}）", config.getStorageKeyPrefix());
        } catch (Exception e) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_DESTROY_FAILED,
                    "销毁浏览器存储失败：" + e.getMessage(), e);
        }
    }

    private BrowserStorageResult dispatch(String operation, String payloadJson) throws PersistenceException {
        BrowserStorageTask task = new BrowserStorageTask(
                UUID.randomUUID().toString(), operation, payloadJson);
        BrowserStorageResult result = adapter.dispatch(task);
        if (result == null) {
            throw new PersistenceException(ErrorCode.BROWSER_STORAGE_UNAVAILABLE,
                    "扩展未响应，请确认扩展已连接");
        }
        if (!result.isSuccess()) {
            // 根据扩展返回的 errorCode 映射到 SDK 错误码
            ErrorCode code = mapErrorCode(result.getErrorCode());
            throw new PersistenceException(code, result.getErrorMessage());
        }
        return result;
    }

    private ErrorCode mapErrorCode(String extErrorCode) {
        if (extErrorCode == null) return ErrorCode.PERSISTENCE_WRITE_FAILED;
        switch (extErrorCode) {
            case "QUOTA_EXCEEDED": return ErrorCode.BROWSER_STORAGE_QUOTA;
            case "STORAGE_UNAVAILABLE": return ErrorCode.BROWSER_STORAGE_UNAVAILABLE;
            case "NOT_FOUND": return ErrorCode.CONVERSATION_NOT_FOUND;
            default: return ErrorCode.PERSISTENCE_WRITE_FAILED;
        }
    }

    private void ensureInitialized() throws PersistenceException {
        if (!initialized) {
            throw new PersistenceException(ErrorCode.PERSISTENCE_NOT_CONFIGURED,
                    "浏览器存储未初始化，请先调用 initialize()");
        }
    }
}
