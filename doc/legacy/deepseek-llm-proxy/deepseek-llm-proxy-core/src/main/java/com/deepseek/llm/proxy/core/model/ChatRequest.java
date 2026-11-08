package com.deepseek.llm.proxy.core.model;

import java.util.List;
import java.util.Map;

/**
 * 聊天请求
 * <p>
 * 客户端通过此对象发起对话，支持流式和同步两种调用方式。
 * </p>
 */
public class ChatRequest {

    /** Provider ID，如 "deepseek-free" */
    private String providerId;
    /** 会话 ID（用于持久化和会话隔离） */
    private String sessionId;
    /** 用户 ID */
    private String userId;
    /** 租户 ID（多租户隔离） */
    private String tenantId;
    /** 用户消息内容 */
    private String content;
    /** 图片列表（多图 OCR / 视觉理解） */
    private List<ImageData> images;
    /** 文件列表（PDF/Word/TXT 等） */
    private List<FileData> files;
    /** 是否开启深度思考（null 表示使用 Provider 默认） */
    private Boolean enableThinking;
    /** 对话模式：default / expert / vision / web / creative */
    private String mode;
    /** 是否开启记忆化（true 沿用对话历史 / false 新会话） */
    private Boolean enableMemory;
    /** 工具列表（Agent 模式） */
    private List<ToolDefinition> tools;
    /** 系统提示词 */
    private String systemPrompt;
    /** 提示词模板 ID（优先级高于 systemPrompt；如 "chat-default" / "ocr-structured"） */
    private String promptId;
    /** 提示词模板变量（与 promptId 配合使用） */
    private Map<String, Object> promptVariables;
    /** 手动注入历史（enableMemory=false 时使用） */
    private List<HistoryMessage> history;
    /** 超时时间（毫秒），默认 300000 */
    private Long timeoutMs;
    /** Webhook 回调 URL（异步任务完成后回调） */
    private String webhookUrl;
    /** 扩展元数据 */
    private Map<String, Object> metadata;

    public String getProviderId() { return providerId; }
    public void setProviderId(String providerId) { this.providerId = providerId; }
    public String getSessionId() { return sessionId; }
    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }
    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
    public List<ImageData> getImages() { return images; }
    public void setImages(List<ImageData> images) { this.images = images; }
    public List<FileData> getFiles() { return files; }
    public void setFiles(List<FileData> files) { this.files = files; }
    public Boolean getEnableThinking() { return enableThinking; }
    public void setEnableThinking(Boolean enableThinking) { this.enableThinking = enableThinking; }
    public String getMode() { return mode; }
    public void setMode(String mode) { this.mode = mode; }
    public Boolean getEnableMemory() { return enableMemory; }
    public void setEnableMemory(Boolean enableMemory) { this.enableMemory = enableMemory; }
    public List<ToolDefinition> getTools() { return tools; }
    public void setTools(List<ToolDefinition> tools) { this.tools = tools; }
    public String getSystemPrompt() { return systemPrompt; }
    public void setSystemPrompt(String systemPrompt) { this.systemPrompt = systemPrompt; }
    public String getPromptId() { return promptId; }
    public void setPromptId(String promptId) { this.promptId = promptId; }
    public Map<String, Object> getPromptVariables() { return promptVariables; }
    public void setPromptVariables(Map<String, Object> promptVariables) { this.promptVariables = promptVariables; }
    public List<HistoryMessage> getHistory() { return history; }
    public void setHistory(List<HistoryMessage> history) { this.history = history; }
    public Long getTimeoutMs() { return timeoutMs; }
    public void setTimeoutMs(Long timeoutMs) { this.timeoutMs = timeoutMs; }
    public String getWebhookUrl() { return webhookUrl; }
    public void setWebhookUrl(String webhookUrl) { this.webhookUrl = webhookUrl; }
    public Map<String, Object> getMetadata() { return metadata; }
    public void setMetadata(Map<String, Object> metadata) { this.metadata = metadata; }

    /** 链式 Builder */
    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private final ChatRequest req = new ChatRequest();

        public Builder providerId(String v) { req.providerId = v; return this; }
        public Builder sessionId(String v) { req.sessionId = v; return this; }
        public Builder userId(String v) { req.userId = v; return this; }
        public Builder tenantId(String v) { req.tenantId = v; return this; }
        public Builder content(String v) { req.content = v; return this; }
        public Builder images(List<ImageData> v) { req.images = v; return this; }
        public Builder files(List<FileData> v) { req.files = v; return this; }
        public Builder enableThinking(Boolean v) { req.enableThinking = v; return this; }
        public Builder mode(String v) { req.mode = v; return this; }
        public Builder enableMemory(Boolean v) { req.enableMemory = v; return this; }
        public Builder tools(List<ToolDefinition> v) { req.tools = v; return this; }
        public Builder systemPrompt(String v) { req.systemPrompt = v; return this; }
        public Builder promptId(String v) { req.promptId = v; return this; }
        public Builder promptVariables(Map<String, Object> v) { req.promptVariables = v; return this; }
        public Builder history(List<HistoryMessage> v) { req.history = v; return this; }
        public Builder timeoutMs(Long v) { req.timeoutMs = v; return this; }
        public Builder webhookUrl(String v) { req.webhookUrl = v; return this; }
        public Builder metadata(Map<String, Object> v) { req.metadata = v; return this; }

        public ChatRequest build() {
            return req;
        }
    }
}
