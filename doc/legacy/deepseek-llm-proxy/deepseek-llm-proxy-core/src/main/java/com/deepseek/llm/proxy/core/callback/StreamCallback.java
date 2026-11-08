package com.deepseek.llm.proxy.core.callback;

import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import com.deepseek.llm.proxy.core.model.FullResponse;
import com.deepseek.llm.proxy.core.model.ToolCall;
import com.deepseek.llm.proxy.core.model.ToolResult;

/**
 * 流式对话回调
 */
public interface StreamCallback {

    /**
     * 深度思考增量
     * @param delta 本次新增的思考文本
     */
    default void onThinking(String delta) {}

    /**
     * 正式回复增量
     * @param delta 本次新增的回复文本
     */
    default void onChunk(String delta) {}

    /**
     * 工具调用（Agent 模式）
     */
    default void onToolCall(ToolCall call) {}

    /**
     * 工具执行结果
     */
    default void onToolResult(ToolResult result) {}

    /**
     * 流式结束，返回完整响应
     */
    default void onComplete(FullResponse response) {}

    /**
     * 错误回调
     */
    default void onError(LlmProxyException e) {}
}
