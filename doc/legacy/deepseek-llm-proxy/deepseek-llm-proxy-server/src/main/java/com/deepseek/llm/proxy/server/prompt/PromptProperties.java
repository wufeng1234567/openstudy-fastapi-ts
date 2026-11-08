package com.deepseek.llm.proxy.server.prompt;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 提示词配置属性
 * <p>
 * 配置前缀：{@code deepseek.llm-proxy.prompt}
 * </p>
 */
@ConfigurationProperties(prefix = "deepseek.llm-proxy.prompt")
public class PromptProperties {

    /** 是否启用提示词管理 */
    private boolean enabled = true;

    /** classpath 下的提示词目录（默认 prompts） */
    private String classpathLocation = "prompts";

    /** 外部文件系统目录（可选，支持热加载）；不配则只用 classpath */
    private String externalLocation;

    /** 是否开启热加载（每 30s 扫描外部目录） */
    private boolean autoReload = false;

    /** 热加载扫描间隔（毫秒），默认 30000 */
    private long reloadIntervalMs = 30000L;

    /** 默认 chat 场景提示词 ID（ChatService 在未指定 promptId 时使用） */
    private String defaultChatPromptId = "chat-default";

    /** 默认 OCR 场景提示词 ID */
    private String defaultOcrPromptId = "ocr-default";

    /** 默认结构化 OCR 提示词 ID */
    private String defaultOcrStructuredPromptId = "ocr-structured";

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
    public String getClasspathLocation() { return classpathLocation; }
    public void setClasspathLocation(String classpathLocation) { this.classpathLocation = classpathLocation; }
    public String getExternalLocation() { return externalLocation; }
    public void setExternalLocation(String externalLocation) { this.externalLocation = externalLocation; }
    public boolean isAutoReload() { return autoReload; }
    public void setAutoReload(boolean autoReload) { this.autoReload = autoReload; }
    public long getReloadIntervalMs() { return reloadIntervalMs; }
    public void setReloadIntervalMs(long reloadIntervalMs) { this.reloadIntervalMs = reloadIntervalMs; }
    public String getDefaultChatPromptId() { return defaultChatPromptId; }
    public void setDefaultChatPromptId(String defaultChatPromptId) { this.defaultChatPromptId = defaultChatPromptId; }
    public String getDefaultOcrPromptId() { return defaultOcrPromptId; }
    public void setDefaultOcrPromptId(String defaultOcrPromptId) { this.defaultOcrPromptId = defaultOcrPromptId; }
    public String getDefaultOcrStructuredPromptId() { return defaultOcrStructuredPromptId; }
    public void setDefaultOcrStructuredPromptId(String defaultOcrStructuredPromptId) { this.defaultOcrStructuredPromptId = defaultOcrStructuredPromptId; }

    /** ClasspathPromptLoader 内部访问 classpathLocation 的便捷方法 */
    public String getClasspathLocationForLoader() {
        return classpathLocation;
    }
}
