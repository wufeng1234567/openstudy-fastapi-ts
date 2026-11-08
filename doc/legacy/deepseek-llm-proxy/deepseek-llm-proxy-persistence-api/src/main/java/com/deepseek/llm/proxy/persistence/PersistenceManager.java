package com.deepseek.llm.proxy.persistence;

import com.deepseek.llm.proxy.core.enums.PersistenceType;
import com.deepseek.llm.proxy.core.exception.PersistenceException;

/**
 * 持久化管理器（策略路由）
 * <p>
 * 根据配置 {@link PersistenceConfig#getType()} 路由到具体策略实现。
 * </p>
 */
public interface PersistenceManager {

    /**
     * 获取当前生效的策略
     */
    PersistenceStrategy getStrategy();

    /**
     * 获取当前存储类型
     */
    PersistenceType getType();

    /**
     * 初始化（执行 initialize + 冲突检测）
     *
     * @throws PersistenceException 初始化失败
     */
    void initialize() throws PersistenceException;

    /**
     * 健康检查
     */
    boolean isHealthy();

    /**
     * 销毁存储
     */
    void destroy() throws PersistenceException;

    /**
     * 是否启用持久化
     */
    default boolean isEnabled() {
        return getType() != PersistenceType.NONE;
    }
}
