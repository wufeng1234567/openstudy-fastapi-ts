package com.deepseek.llm.proxy.persistence;

import com.deepseek.llm.proxy.core.enums.PersistenceType;
import com.deepseek.llm.proxy.core.exception.PersistenceException;
import com.deepseek.llm.proxy.core.model.Conversation;
import com.deepseek.llm.proxy.core.model.MemoryRecord;

import java.util.List;
import java.util.Optional;

/**
 * 持久化策略接口（双存储范式抽象）
 * <p>
 * 实现类：
 * <ul>
 *   <li>{@code BrowserPersistenceStrategy}：浏览器本地化存储（IndexedDB / chrome.storage，由扩展 JS 实现）</li>
 *   <li>{@code SqlPersistenceStrategy}：SQL 数据库存储（JDBC）</li>
 *   <li>{@code NoopPersistenceStrategy}：不持久化（默认）</li>
 * </ul>
 * </p>
 * <p>
 * 开发者通过配置 {@code deepseek.llm-proxy.persistence.type} 选择实现，SDK 自动装配。
 * </p>
 */
public interface PersistenceStrategy {

    /**
     * 当前存储类型
     */
    PersistenceType getType();

    /**
     * 初始化存储
     * <ul>
     *   <li>Browser：创建 IndexedDB store</li>
     *   <li>SQL：建表 / 校验 schema / 检测冲突</li>
     * </ul>
     *
     * @throws PersistenceException 初始化失败，包含具体原因和修复建议
     */
    void initialize() throws PersistenceException;

    /**
     * 健康检查
     */
    boolean isHealthy();

    /**
     * 保存会话（upsert）
     */
    void saveConversation(Conversation conversation) throws PersistenceException;

    /**
     * 加载会话
     */
    Optional<Conversation> loadConversation(String sessionId) throws PersistenceException;

    /**
     * 列出用户的所有会话
     *
     * @param userId 用户 ID
     * @param limit  最大返回数
     * @param offset 偏移量（分页）
     */
    List<Conversation> listConversations(String userId, int limit, int offset) throws PersistenceException;

    /**
     * 删除会话
     *
     * @return true 删除成功 / false 会话不存在
     */
    boolean deleteConversation(String sessionId) throws PersistenceException;

    /**
     * 保存记忆（upsert，按 userId + providerId）
     */
    void saveMemory(MemoryRecord memory) throws PersistenceException;

    /**
     * 加载记忆
     */
    Optional<MemoryRecord> loadMemory(String userId, String providerId) throws PersistenceException;

    /**
     * 清空记忆
     *
     * @return true 清空成功 / false 记忆不存在
     */
    boolean clearMemory(String userId, String providerId) throws PersistenceException;

    /**
     * 销毁存储（drop 表 / 删 IndexedDB）
     * <p>谨慎调用，会丢失全部数据。</p>
     */
    void destroy() throws PersistenceException;
}
