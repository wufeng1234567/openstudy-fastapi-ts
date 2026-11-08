package com.deepseek.llm.proxy.core.enums;

/**
 * Provider 能力枚举
 * <p>用于声明 Provider 支持的功能集，客户端通过 getCapabilities() 动态适配。</p>
 */
public enum Capability {
    /** 支持图片输入（多图 OCR / 视觉理解） */
    IMAGES,
    /** 支持文件输入（PDF/Word/TXT 等） */
    FILES,
    /** 支持深度思考输出（reasoning 阶段） */
    THINKING,
    /** 支持多种对话模式（default/expert/vision 等） */
    MODES,
    /** 支持工具调用（Agent Loop） */
    TOOLS,
    /** 支持记忆化（跨会话记忆） */
    MEMORY,
    /** 支持流式输出 */
    STREAMING,
    /** 支持 OCR 结构化输出 */
    OCR_STRUCTURED
}
