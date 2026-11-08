package com.deepseek.llm.proxy.core.model;

import java.time.Instant;
import java.util.Map;

/**
 * 服务状态
 */
public class ProxyStatus {

    /** 服务是否可用 */
    private boolean available;
    /** 在线 Provider 数量 */
    private int onlineProviders;
    /** 活跃任务数 */
    private int activeTasks;
    /** 最近一次心跳时间 */
    private Instant lastHeartbeat;
    /** API 版本 */
    private String apiVersion;
    /** 扩展状态（如已连接 / 未连接） */
    private Map<String, Object> extensionStatus;
    /** 元数据 */
    private Map<String, Object> metadata;

    public boolean isAvailable() { return available; }
    public void setAvailable(boolean available) { this.available = available; }
    public int getOnlineProviders() { return onlineProviders; }
    public void setOnlineProviders(int onlineProviders) { this.onlineProviders = onlineProviders; }
    public int getActiveTasks() { return activeTasks; }
    public void setActiveTasks(int activeTasks) { this.activeTasks = activeTasks; }
    public Instant getLastHeartbeat() { return lastHeartbeat; }
    public void setLastHeartbeat(Instant lastHeartbeat) { this.lastHeartbeat = lastHeartbeat; }
    public String getApiVersion() { return apiVersion; }
    public void setApiVersion(String apiVersion) { this.apiVersion = apiVersion; }
    public Map<String, Object> getExtensionStatus() { return extensionStatus; }
    public void setExtensionStatus(Map<String, Object> extensionStatus) { this.extensionStatus = extensionStatus; }
    public Map<String, Object> getMetadata() { return metadata; }
    public void setMetadata(Map<String, Object> metadata) { this.metadata = metadata; }
}
