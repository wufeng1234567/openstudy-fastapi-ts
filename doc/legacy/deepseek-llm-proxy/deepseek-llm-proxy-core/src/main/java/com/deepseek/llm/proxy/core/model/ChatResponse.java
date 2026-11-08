package com.deepseek.llm.proxy.core.model;

import java.time.Instant;
import java.util.Map;

/**
 * 聊天响应（同步调用返回）
 */
public class ChatResponse {

    private String requestId;
    private String sessionId;
    private String providerId;
    private String content;
    private String thinkingContent;
    private Instant completedAt;
    private Map<String, Object> metadata;

    public String getRequestId() { return requestId; }
    public void setRequestId(String requestId) { this.requestId = requestId; }
    public String getSessionId() { return sessionId; }
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    public String getProviderId() { return providerId; }
    public void setProviderId(String providerId) { this.providerId = providerId; }
    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
    public String getThinkingContent() { return thinkingContent; }
    public void setThinkingContent(String thinkingContent) { this.thinkingContent = thinkingContent; }
    public Instant getCompletedAt() { return completedAt; }
    public void setCompletedAt(Instant completedAt) { this.completedAt = completedAt; }
    public Map<String, Object> getMetadata() { return metadata; }
    public void setMetadata(Map<String, Object> metadata) { this.metadata = metadata; }
}
