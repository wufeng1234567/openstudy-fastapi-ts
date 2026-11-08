package com.deepseek.llm.proxy.core.model;

import java.util.Objects;

/**
 * 工具执行结果
 */
public class ToolResult {

    /** 关联的工具调用 ID */
    private String callId;
    /** 工具名称 */
    private String tool;
    /** 是否执行成功 */
    private boolean success;
    /** 执行消息（成功提示 / 失败原因） */
    private String message;
    /** 结果数据（JSON 字符串或对象） */
    private Object data;
    /** 是否需要用户确认 */
    private boolean pendingConfirmation;

    public ToolResult() {
    }

    public static ToolResult success(String tool, Object data) {
        ToolResult r = new ToolResult();
        r.tool = tool;
        r.success = true;
        r.data = data;
        return r;
    }

    public static ToolResult failure(String tool, String message) {
        ToolResult r = new ToolResult();
        r.tool = tool;
        r.success = false;
        r.message = message;
        return r;
    }

    public String getCallId() { return callId; }
    public void setCallId(String callId) { this.callId = callId; }
    public String getTool() { return tool; }
    public void setTool(String tool) { this.tool = tool; }
    public boolean isSuccess() { return success; }
    public void setSuccess(boolean success) { this.success = success; }
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
    public Object getData() { return data; }
    public void setData(Object data) { this.data = data; }
    public boolean isPendingConfirmation() { return pendingConfirmation; }
    public void setPendingConfirmation(boolean pendingConfirmation) { this.pendingConfirmation = pendingConfirmation; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        ToolResult that = (ToolResult) o;
        return success == that.success
                && Objects.equals(callId, that.callId)
                && Objects.equals(tool, that.tool);
    }

    @Override
    public int hashCode() {
        return Objects.hash(callId, tool, success);
    }
}
