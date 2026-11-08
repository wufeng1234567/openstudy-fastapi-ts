package com.deepseek.llm.proxy.persistence.browser;

/**
 * 浏览器存储适配器
 * <p>
 * 此接口为 Java 端契约，实际由浏览器扩展 JS 端实现。
 * Java 端通过 WebSocket / HTTP 把任务下发给扩展执行。
 * </p>
 * <p>
 * 后端实现类（阶段 2 实现）：通过 WebSocket 把任务推送给扩展，
 * 扩展返回 {@link BrowserStorageResult}。
 * </p>
 * <p>
 * 扩展端实现：extension/core/persistence/BrowserPersistenceAdapter.js（IndexedDB）
 * </p>
 */
public interface BrowserStorageAdapter {

    /**
     * 派发存储任务到浏览器扩展执行
     *
     * @param task 任务
     * @return 执行结果
     */
    BrowserStorageResult dispatch(BrowserStorageTask task);

    /**
     * 异步派发（带超时）
     *
     * @param task      任务
     * @param timeoutMs 超时时间
     */
    BrowserStorageResult dispatch(BrowserStorageTask task, long timeoutMs);

    /**
     * 扩展是否在线
     */
    boolean isExtensionOnline();
}
