package com.deepseek.llm.proxy.core.model;

import java.time.Instant;
import java.util.Map;
import java.util.Objects;

/**
 * 记忆记录（持久化数据模型）
 * <p>跨会话的长效记忆，与 Conversation 不同：一个用户每 Provider 一条记忆。</p>
 */
public class MemoryRecord {

    /** 用户 ID */
    private String userId;
    /** 租户 ID */
    private String tenantId;
    /** Provider ID */
    private String providerId;
    /** 记忆内容 */
    private String content;
    /** 扩展字段 */
    private Map<String, Object> metadata;
    /** 创建时间 */
    private Instant createdAt;
    /** 更新时间 */
    private Instant updatedAt;

    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }
    public String getProviderId() { return providerId; }
    public void setProviderId(String providerId) { this.providerId = providerId; }
    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
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
        MemoryRecord that = (MemoryRecord) o;
        return Objects.equals(userId, that.userId)
                && Objects.equals(providerId, that.providerId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(userId, providerId);
    }
}
