package com.deepseek.llm.proxy.core.exception;

import com.deepseek.llm.proxy.core.enums.ErrorCode;

/**
 * LLM Proxy 异常基类
 * <p>所有 SDK 抛出的异常都继承自此类，携带 ErrorCode 用于客户端识别处理。</p>
 */
public class LlmProxyException extends Exception {

    private static final long serialVersionUID = 1L;

    private final ErrorCode errorCode;
    private final String detail;

    public LlmProxyException(ErrorCode errorCode) {
        this(errorCode, null, null);
    }

    public LlmProxyException(ErrorCode errorCode, String detail) {
        this(errorCode, detail, null);
    }

    public LlmProxyException(ErrorCode errorCode, String detail, Throwable cause) {
        super(buildMessage(errorCode, detail), cause);
        this.errorCode = errorCode;
        this.detail = detail;
    }

    private static String buildMessage(ErrorCode errorCode, String detail) {
        if (detail == null || detail.isEmpty()) {
            return "[" + errorCode.getCode() + ":" + errorCode.getName() + "] " + errorCode.getMessage();
        }
        return "[" + errorCode.getCode() + ":" + errorCode.getName() + "] " + errorCode.getMessage() + " - " + detail;
    }

    public ErrorCode getErrorCode() {
        return errorCode;
    }

    public String getDetail() {
        return detail;
    }
}
