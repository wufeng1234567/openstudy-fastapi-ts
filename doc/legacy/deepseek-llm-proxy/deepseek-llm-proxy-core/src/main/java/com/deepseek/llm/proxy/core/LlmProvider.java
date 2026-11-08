package com.deepseek.llm.proxy.core;

import com.deepseek.llm.proxy.core.enums.Capability;
import com.deepseek.llm.proxy.core.enums.ProviderMode;

import java.util.List;
import java.util.Set;

/**
 * LLM Provider 抽象接口
 * <p>
 * 每个具体 Provider（如 DeepSeek 网页版、Claude 网页版、OpenAI API 等）实现此接口，
 * 声明自身的能力集和支持的模式，供客户端动态适配。
 * </p>
 */
public interface LlmProvider {

    /**
     * Provider 唯一标识，如 "deepseek-free"
     */
    String getId();

    /**
     * 展示名称，如 "DeepSeek Free"
     */
    String getDisplayName();

    /**
     * 能力集合
     */
    Set<Capability> getCapabilities();

    /**
     * 支持的模式列表
     */
    List<ProviderMode> getSupportedModes();

    /** 是否支持图片输入 */
    default boolean supportsImages() {
        return getCapabilities().contains(Capability.IMAGES);
    }

    /** 是否支持深度思考 */
    default boolean supportsThinking() {
        return getCapabilities().contains(Capability.THINKING);
    }

    /** 是否支持文件输入 */
    default boolean supportsFiles() {
        return getCapabilities().contains(Capability.FILES);
    }

    /** 是否支持工具调用 */
    default boolean supportsTools() {
        return getCapabilities().contains(Capability.TOOLS);
    }

    /** 是否支持记忆化 */
    default boolean supportsMemory() {
        return getCapabilities().contains(Capability.MEMORY);
    }

    /** 是否支持流式输出 */
    default boolean supportsStreaming() {
        return getCapabilities().contains(Capability.STREAMING);
    }

    /** 是否支持 OCR 结构化输出 */
    default boolean supportsOcrStructured() {
        return getCapabilities().contains(Capability.OCR_STRUCTURED);
    }
}
