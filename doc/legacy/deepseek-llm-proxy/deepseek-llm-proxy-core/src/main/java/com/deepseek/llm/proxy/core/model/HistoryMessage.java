package com.deepseek.llm.proxy.core.model;

import java.time.Instant;
import java.util.Objects;

/**
 * 历史消息（用于 ChatRequest.history 手动注入，或持久化存储）
 */
public class HistoryMessage {

    /** 角色：user / assistant / system / tool */
    private String role;
    /** 消息正文 */
    private String content;
    /** 深度思考内容（可选，仅 assistant 角色） */
    private String thinkingContent;
    /** 工具调用 ID（可选，仅 tool 角色） */
    private String toolCallId;
    /** 工具名称（可选） */
    private String toolName;
    /** 工具参数 JSON（可选） */
    private String toolParamsJson;
    /** 工具结果 JSON（可选） */
    private String toolResultJson;
    /** 消息时间戳 */
    private Instant timestamp;

    public HistoryMessage() {
    }

    public static HistoryMessage user(String content) {
        HistoryMessage m = new HistoryMessage();
        m.role = "user";
        m.content = content;
        m.timestamp = Instant.now();
        return m;
    }

    public static HistoryMessage assistant(String content) {
        HistoryMessage m = new HistoryMessage();
        m.role = "assistant";
        m.content = content;
        m.timestamp = Instant.now();
        return m;
    }

    public static HistoryMessage system(String content) {
        HistoryMessage m = new HistoryMessage();
        m.role = "system";
        m.content = content;
        m.timestamp = Instant.now();
        return m;
    }

    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }
    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
    public String getThinkingContent() { return thinkingContent; }
    public void setThinkingContent(String thinkingContent) { this.thinkingContent = thinkingContent; }
    public String getToolCallId() { return toolCallId; }
    public void setToolCallId(String toolCallId) { this.toolCallId = toolCallId; }
    public String getToolName() { return toolName; }
    public void setToolName(String toolName) { this.toolName = toolName; }
    public String getToolParamsJson() { return toolParamsJson; }
    public void setToolParamsJson(String toolParamsJson) { this.toolParamsJson = toolParamsJson; }
    public String getToolResultJson() { return toolResultJson; }
    public void setToolResultJson(String toolResultJson) { this.toolResultJson = toolResultJson; }
    public Instant getTimestamp() { return timestamp; }
    public void setTimestamp(Instant timestamp) { this.timestamp = timestamp; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        HistoryMessage that = (HistoryMessage) o;
        return Objects.equals(role, that.role)
                && Objects.equals(content, that.content)
                && Objects.equals(thinkingContent, that.thinkingContent)
                && Objects.equals(toolCallId, that.toolCallId)
                && Objects.equals(timestamp, that.timestamp);
    }

    @Override
    public int hashCode() {
        return Objects.hash(role, content, thinkingContent, toolCallId, timestamp);
    }
}
