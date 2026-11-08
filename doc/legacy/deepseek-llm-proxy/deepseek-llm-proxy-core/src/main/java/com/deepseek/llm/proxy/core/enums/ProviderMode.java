package com.deepseek.llm.proxy.core.enums;

/**
 * Provider 对话模式
 * <p>不同 Provider 支持的模式不同，通过 LlmProvider.getSupportedModes() 声明。</p>
 */
public enum ProviderMode {
    /** 默认模式 */
    DEFAULT("default"),
    /** 专家模式（推理增强） */
    EXPERT("expert"),
    /** 视觉模式（图片理解） */
    VISION("vision"),
    /** 联网模式 */
    WEB("web"),
    /** 创意模式 */
    CREATIVE("creative");

    private final String code;

    ProviderMode(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public static ProviderMode fromCode(String code) {
        if (code == null) {
            return null;
        }
        for (ProviderMode m : values()) {
            if (m.code.equalsIgnoreCase(code)) {
                return m;
            }
        }
        return null;
    }
}
