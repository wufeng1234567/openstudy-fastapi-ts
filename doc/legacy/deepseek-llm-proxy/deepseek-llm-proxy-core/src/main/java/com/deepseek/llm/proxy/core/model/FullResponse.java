package com.deepseek.llm.proxy.core.model;

import java.time.Instant;
import java.util.Objects;

/**
 * 完整响应（流式对话结束后回调 onComplete 的参数）
 */
public class FullResponse {

    /** 请求 ID */
    private String requestId;
    /** 会话 ID */
    private String sessionId;
    /** Provider ID */
    private String providerId;
    /** 完整回复文本（不含思考） */
    private String content;
    /** 完整深度思考文本 */
    private String thinkingContent;
    /** 完成时间 */
    private Instant completedAt;
    /** 是否触发工具调用 */
    private boolean hasToolCall;
    /** 工具调用（如有） */
    private ToolCall toolCall;
    /** 元数据 */
    private java.util.Map<String, Object> metadata;

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
    public boolean isHasToolCall() { return hasToolCall; }
    public void setHasToolCall(boolean hasToolCall) { this.hasToolCall = hasToolCall; }
    public ToolCall getToolCall() { return toolCall; }
    public void setToolCall(ToolCall toolCall) { this.toolCall = toolCall; }
    public java.util.Map<String, Object> getMetadata() { return metadata; }
    public void setMetadata(java.util.Map<String, Object> metadata) { this.metadata = metadata; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        return Objects.equals(requestId, ((FullResponse) o).requestId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(requestId);
    }
}
