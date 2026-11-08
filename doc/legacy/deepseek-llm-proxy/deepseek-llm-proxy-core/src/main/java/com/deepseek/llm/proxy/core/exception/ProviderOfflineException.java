package com.deepseek.llm.proxy.core.exception;

import com.deepseek.llm.proxy.core.enums.ErrorCode;

/**
 * Provider 离线异常
 * <p>扩展未连接 / Provider 网页未打开 / 网页登录失效时抛出。</p>
 */
public class ProviderOfflineException extends LlmProxyException {

    private static final long serialVersionUID = 1L;

    private final String providerId;

    public ProviderOfflineException(String providerId) {
        super(ErrorCode.PROVIDER_OFFLINE, "provider=" + providerId);
        this.providerId = providerId;
    }

    public ProviderOfflineException(String providerId, String detail) {
        super(ErrorCode.PROVIDER_OFFLINE, "provider=" + providerId + ", " + detail);
        this.providerId = providerId;
    }

    public String getProviderId() {
        return providerId;
    }
}
