package com.deepseek.llm.proxy.core.model;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * 对话会话（持久化数据模型）
 */
public class Conversation {

    /** 会话 ID（UUID） */
    private String sessionId;
    /** 用户 ID */
    private String userId;
    /** 租户 ID */
    private String tenantId;
    /** Provider ID */
    private String providerId;
    /** 会话标题 */
    private String title;
    /** 消息列表 */
    private List<HistoryMessage> messages;
    /** 扩展字段 */
    private Map<String, Object> metadata;
    /** 创建时间 */
    private Instant createdAt;
    /** 更新时间 */
    private Instant updatedAt;

    public String getSessionId() { return sessionId; }
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }
    public String getProviderId() { return providerId; }
    public void setProviderId(String providerId) { this.providerId = providerId; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public List<HistoryMessage> getMessages() { return messages; }
    public void setMessages(List<HistoryMessage> messages) { this.messages = messages; }
    public Map<String, Object> getMetadata() { return metadata; }
    public void setMetadata(Map<String, Object> metadata) { this.metadata = metadata; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant updatedAt) { this.updatedAt = updatedAt; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        return Objects.equals(sessionId, ((Conversation) o).sessionId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(sessionId);
    }
}
