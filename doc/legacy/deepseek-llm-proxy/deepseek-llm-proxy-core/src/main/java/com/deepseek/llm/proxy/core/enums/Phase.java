package com.deepseek.llm.proxy.core.enums;

/**
 * 流式输出阶段
 * <p>用于区分深度思考阶段与正式回复阶段。</p>
 */
public enum Phase {
    /** 深度思考阶段（reasoning） */
    THINKING,
    /** 正式回复阶段 */
    RESPONSE,
    /** 工具调用阶段 */
    TOOL_CALL,
    /** 工具结果阶段 */
    TOOL_RESULT
}
