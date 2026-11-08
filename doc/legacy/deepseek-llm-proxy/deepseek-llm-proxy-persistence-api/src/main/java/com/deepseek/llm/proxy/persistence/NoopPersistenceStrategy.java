package com.deepseek.llm.proxy.persistence;

import com.deepseek.llm.proxy.core.enums.PersistenceType;
import com.deepseek.llm.proxy.core.exception.PersistenceException;

import java.util.Optional;

/**
 * No-op 持久化策略（默认实现，不做任何持久化）
 */
public class NoopPersistenceStrategy implements PersistenceStrategy {

    @Override
    public PersistenceType getType() {
        return PersistenceType.NONE;
    }

    @Override
    public void initialize() {
        // 无操作
    }

    @Override
    public boolean isHealthy() {
        return true;
    }

    @Override
    public void saveConversation(com.deepseek.llm.proxy.core.model.Conversation conversation) {
        // 无操作
    }

    @Override
    public Optional<com.deepseek.llm.proxy.core.model.Conversation> loadConversation(String sessionId) {
        return Optional.empty();
    }

    @Override
    public java.util.List<com.deepseek.llm.proxy.core.model.Conversation> listConversations(String userId, int limit, int offset) {
        return java.util.Collections.emptyList();
    }

    @Override
    public boolean deleteConversation(String sessionId) {
        return false;
    }

    @Override
    public void saveMemory(com.deepseek.llm.proxy.core.model.MemoryRecord memory) {
        // 无操作
    }

    @Override
    public Optional<com.deepseek.llm.proxy.core.model.MemoryRecord> loadMemory(String userId, String providerId) {
        return Optional.empty();
    }

    @Override
    public boolean clearMemory(String userId, String providerId) {
        return false;
    }

    @Override
    public void destroy() {
        // 无操作
    }
}
