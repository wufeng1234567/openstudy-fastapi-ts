package com.deepseek.llm.proxy.persistence;

import com.deepseek.llm.proxy.core.exception.PersistenceException;
import com.deepseek.llm.proxy.core.model.MemoryRecord;

import java.util.Optional;

/**
 * 记忆仓库接口
 */
public interface MemoryRepository {

    void save(MemoryRecord memory) throws PersistenceException;

    Optional<MemoryRecord> findByUserIdAndProvider(String userId, String providerId) throws PersistenceException;

    boolean clear(String userId, String providerId) throws PersistenceException;
}
