package com.deepseek.llm.proxy.core.exception;

import com.deepseek.llm.proxy.core.enums.ErrorCode;

/**
 * 持久化异常
 * <p>所有持久化相关错误（初始化失败、读写失败、表冲突等）的基类。</p>
 */
public class PersistenceException extends LlmProxyException {

    private static final long serialVersionUID = 1L;

    public PersistenceException(ErrorCode errorCode) {
        super(errorCode);
    }

    public PersistenceException(ErrorCode errorCode, String detail) {
        super(errorCode, detail);
    }

    public PersistenceException(ErrorCode errorCode, String detail, Throwable cause) {
        super(errorCode, detail, cause);
    }
}
