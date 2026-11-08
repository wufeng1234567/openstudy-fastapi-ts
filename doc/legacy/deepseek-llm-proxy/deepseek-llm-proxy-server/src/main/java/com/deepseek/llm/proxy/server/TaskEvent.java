package com.deepseek.llm.proxy.server;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.enums.Phase;
import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import com.deepseek.llm.proxy.core.model.FullResponse;
import com.deepseek.llm.proxy.core.model.ToolCall;
import com.deepseek.llm.proxy.core.model.ToolResult;

/**
 * 任务事件（推送给 SSE 订阅者）
 * <p>对应 SSE 事件类型：running / chunk / tool_call / tool_result / complete / error / cancelled</p>
 */
public class TaskEvent {

    public enum Type {
        RUNNING, CHUNK, TOOL_CALL, TOOL_RESULT, COMPLETE, ERROR, CANCELLED
    }

    private final Type type;
    private final String taskId;
    private final Phase phase;            // CHUNK 时有效
    private final String delta;           // CHUNK 时有效
    private final String cumulative;      // CHUNK 时有效
    private final FullResponse fullResponse; // COMPLETE 时有效
    private final ToolCall toolCall;      // TOOL_CALL 时有效
    private final ToolResult toolResult;  // TOOL_RESULT 时有效
    private final LlmProxyException error; // ERROR 时有效

    private TaskEvent(Type type, String taskId, Phase phase, String delta, String cumulative,
                      FullResponse fullResponse, ToolCall toolCall, ToolResult toolResult,
                      LlmProxyException error) {
        this.type = type;
        this.taskId = taskId;
        this.phase = phase;
        this.delta = delta;
        this.cumulative = cumulative;
        this.fullResponse = fullResponse;
        this.toolCall = toolCall;
        this.toolResult = toolResult;
        this.error = error;
    }

    public static TaskEvent running(String taskId) {
        return new TaskEvent(Type.RUNNING, taskId, null, null, null, null, null, null, null);
    }

    public static TaskEvent chunk(String taskId, Phase phase, String delta, String cumulative) {
        return new TaskEvent(Type.CHUNK, taskId, phase, delta, cumulative, null, null, null, null);
    }

    public static TaskEvent toolCall(String taskId, ToolCall call) {
        return new TaskEvent(Type.TOOL_CALL, taskId, null, null, null, null, call, null, null);
    }

    public static TaskEvent toolResult(String taskId, ToolResult result) {
        return new TaskEvent(Type.TOOL_RESULT, taskId, null, null, null, null, null, result, null);
    }

    public static TaskEvent complete(String taskId, FullResponse resp) {
        return new TaskEvent(Type.COMPLETE, taskId, null, null, null, resp, null, null, null);
    }

    public static TaskEvent error(String taskId, LlmProxyException ex) {
        return new TaskEvent(Type.ERROR, taskId, null, null, null, null, null, null, ex);
    }

    public static TaskEvent cancelled(String taskId) {
        return new TaskEvent(Type.CANCELLED, taskId, null, null, null, null, null, null, null);
    }

    public Type getType() { return type; }
    public String getTaskId() { return taskId; }
    public Phase getPhase() { return phase; }
    public String getDelta() { return delta; }
    public String getCumulative() { return cumulative; }
    public FullResponse getFullResponse() { return fullResponse; }
    public ToolCall getToolCall() { return toolCall; }
    public ToolResult getToolResult() { return toolResult; }
    public LlmProxyException getError() {
        return error != null ? error : new LlmProxyException(ErrorCode.INTERNAL_ERROR, "未知错误");
    }
}
