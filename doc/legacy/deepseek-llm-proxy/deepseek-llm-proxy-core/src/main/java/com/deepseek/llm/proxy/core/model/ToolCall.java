package com.deepseek.llm.proxy.core.model;

import java.util.Objects;

/**
 * 工具调用（LLM 发起的工具调用请求）
 */
public class ToolCall {

    /** 工具名称 */
    private String tool;
    /** 参数 JSON 字符串 */
    private String paramsJson;
    /** 调用 ID（用于关联结果） */
    private String callId;
    /** 原始工具调用文本块（用于显示和回溯） */
    private String rawBlock;

    public ToolCall() {
    }

    public ToolCall(String tool, String paramsJson) {
        this.tool = tool;
        this.paramsJson = paramsJson;
    }

    public String getTool() { return tool; }
    public void setTool(String tool) { this.tool = tool; }
    public String getParamsJson() { return paramsJson; }
    public void setParamsJson(String paramsJson) { this.paramsJson = paramsJson; }
    public String getCallId() { return callId; }
    public void setCallId(String callId) { this.callId = callId; }
    public String getRawBlock() { return rawBlock; }
    public void setRawBlock(String rawBlock) { this.rawBlock = rawBlock; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        ToolCall toolCall = (ToolCall) o;
        return Objects.equals(tool, toolCall.tool)
                && Objects.equals(paramsJson, toolCall.paramsJson);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tool, paramsJson);
    }
}
