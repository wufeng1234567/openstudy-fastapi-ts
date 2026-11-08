package com.deepseek.llm.proxy.core.model;

import java.util.List;
import java.util.Map;

/**
 * OCR 请求
 * <p>支持 1~N 张图片，返回结构化 JSON 或纯文本。</p>
 */
public class OcrRequest {

    /** Provider ID */
    private String providerId;
    /** 用户 ID */
    private String userId;
    /** 租户 ID */
    private String tenantId;
    /** 图片列表（1~N 张） */
    private List<ImageData> images;
    /** 自定义提示词（可选，覆盖默认 OCR 提示词） */
    private String prompt;
    /** 提示词模板 ID（优先级高于 prompt；如 "ocr-default" / "ocr-structured"） */
    private String promptId;
    /** 提示词模板变量（与 promptId 配合使用） */
    private Map<String, Object> promptVariables;
    /** 是否返回结构化 JSON（true JSON / false 纯文本） */
    private Boolean structured;
    /** 是否开启深度思考 */
    private Boolean enableThinking;
    /** 超时时间（毫秒），默认 180000 */
    private Long timeoutMs;
    /** 期望的 JSON Schema（structured=true 时使用，可选） */
    private String expectedSchemaJson;

    public String getProviderId() { return providerId; }
    public void setProviderId(String providerId) { this.providerId = providerId; }
    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }
    public List<ImageData> getImages() { return images; }
    public void setImages(List<ImageData> images) { this.images = images; }
    public String getPrompt() { return prompt; }
    public void setPrompt(String prompt) { this.prompt = prompt; }
    public String getPromptId() { return promptId; }
    public void setPromptId(String promptId) { this.promptId = promptId; }
    public Map<String, Object> getPromptVariables() { return promptVariables; }
    public void setPromptVariables(Map<String, Object> promptVariables) { this.promptVariables = promptVariables; }
    public Boolean getStructured() { return structured; }
    public void setStructured(Boolean structured) { this.structured = structured; }
    public Boolean getEnableThinking() { return enableThinking; }
    public void setEnableThinking(Boolean enableThinking) { this.enableThinking = enableThinking; }
    public Long getTimeoutMs() { return timeoutMs; }
    public void setTimeoutMs(Long timeoutMs) { this.timeoutMs = timeoutMs; }
    public String getExpectedSchemaJson() { return expectedSchemaJson; }
    public void setExpectedSchemaJson(String expectedSchemaJson) { this.expectedSchemaJson = expectedSchemaJson; }

    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private final OcrRequest req = new OcrRequest();

        public Builder providerId(String v) { req.providerId = v; return this; }
        public Builder userId(String v) { req.userId = v; return this; }
        public Builder tenantId(String v) { req.tenantId = v; return this; }
        public Builder images(List<ImageData> v) { req.images = v; return this; }
        public Builder prompt(String v) { req.prompt = v; return this; }
        public Builder promptId(String v) { req.promptId = v; return this; }
        public Builder promptVariables(Map<String, Object> v) { req.promptVariables = v; return this; }
        public Builder structured(Boolean v) { req.structured = v; return this; }
        public Builder enableThinking(Boolean v) { req.enableThinking = v; return this; }
        public Builder timeoutMs(Long v) { req.timeoutMs = v; return this; }
        public Builder expectedSchemaJson(String v) { req.expectedSchemaJson = v; return this; }

        public OcrRequest build() {
            return req;
        }
    }
}
