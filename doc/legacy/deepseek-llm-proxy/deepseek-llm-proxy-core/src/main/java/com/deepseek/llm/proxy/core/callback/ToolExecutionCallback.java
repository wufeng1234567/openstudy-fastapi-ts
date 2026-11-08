package com.deepseek.llm.proxy.core.callback;

import com.deepseek.llm.proxy.core.model.ToolCall;
import com.deepseek.llm.proxy.core.model.ToolResult;

/**
 * 工具执行回调（Agent 模式）
 */
public interface ToolExecutionCallback {

    /**
     * 工具调用前（可用于显示等待状态）
     */
    default void beforeExecute(ToolCall call) {}

    /**
     * 工具执行后
     */
    default void afterExecute(ToolCall call, ToolResult result) {}

    /**
     * 需要用户确认（删除/修改等敏感操作）
     * @return true 确认执行 / false 取消
     */
    default boolean onConfirm(ToolCall call) {
        return true;
    }
}
