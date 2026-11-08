package com.deepseek.llm.proxy.core.prompt;

/**
 * 提示词相关异常
 */
public class PromptException extends RuntimeException {

    public PromptException(String message) {
        super(message);
    }

    public PromptException(String message, Throwable cause) {
        super(message, cause);
    }
}
