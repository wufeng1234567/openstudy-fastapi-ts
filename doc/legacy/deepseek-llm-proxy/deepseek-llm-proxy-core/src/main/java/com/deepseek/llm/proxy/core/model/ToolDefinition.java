package com.deepseek.llm.proxy.core.model;

import java.util.Objects;

/**
 * 工具定义
 * <p>声明可供 LLM 调用的工具，用于 Agent 模式。</p>
 */
public class ToolDefinition {

    /** 工具名称（全局唯一） */
    private String name;
    /** 工具描述 */
    private String description;
    /** 参数 JSON Schema */
    private String paramsSchemaJson;
    /** 是否需要用户确认（删除/修改等敏感操作） */
    private boolean needsConfirmation;

    public ToolDefinition() {
    }

    public ToolDefinition(String name, String description, String paramsSchemaJson) {
        this.name = name;
        this.description = description;
        this.paramsSchemaJson = paramsSchemaJson;
    }

    public static ToolDefinition of(String name, String description) {
        return new ToolDefinition(name, description, "{}");
    }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }
    public String getParamsSchemaJson() { return paramsSchemaJson; }
    public void setParamsSchemaJson(String paramsSchemaJson) { this.paramsSchemaJson = paramsSchemaJson; }
    public boolean isNeedsConfirmation() { return needsConfirmation; }
    public void setNeedsConfirmation(boolean needsConfirmation) { this.needsConfirmation = needsConfirmation; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        return Objects.equals(name, ((ToolDefinition) o).name);
    }

    @Override
    public int hashCode() {
        return Objects.hash(name);
    }
}
