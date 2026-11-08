package com.deepseek.llm.proxy.core.prompt;

import java.util.ArrayList;
import java.util.List;

/**
 * 提示词模板定义
 * <p>
 * 描述一个提示词模板的元信息：ID、归属 Provider、场景、版本、模板内容、声明的变量。
 * </p>
 */
public class PromptDefinition {

    /** 提示词 ID（唯一标识，如 "chat-default"、"ocr-structured"） */
    private String id;

    /** 归属 Provider ID（null 表示通用） */
    private String providerId;

    /** 场景（chat / ocr / translate / summarize 等） */
    private String scene;

    /** 版本号（语义化版本，如 "1.0.0"） */
    private String version;

    /** 模板内容（含占位符） */
    private String content;

    /** 声明的变量名列表 */
    private List<String> variables;

    /** 描述（用于文档展示） */
    private String description;

    /** 来源（classpath / file / api） */
    private String source;

    public PromptDefinition() {
        this.variables = new ArrayList<>();
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getProviderId() { return providerId; }
    public void setProviderId(String providerId) { this.providerId = providerId; }

    public String getScene() { return scene; }
    public void setScene(String scene) { this.scene = scene; }

    public String getVersion() { return version; }
    public void setVersion(String version) { this.version = version; }

    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }

    public List<String> getVariables() { return variables; }
    public void setVariables(List<String> variables) {
        this.variables = variables == null ? new ArrayList<>() : variables;
    }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public String getSource() { return source; }
    public void setSource(String source) { this.source = source; }

    /**
     * 唯一索引键（providerId + ":" + id，providerId 为 null 时用 "_global"）
     */
    public String key() {
        return (providerId == null ? "_global" : providerId) + ":" + id;
    }
}
