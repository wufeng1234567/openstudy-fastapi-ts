package com.deepseek.llm.proxy.core;

/**
 * Provider 健康检查器
 * <p>
 * 运行时探测 Provider 的真实可用性状态，弥补 {@link LlmProvider#getCapabilities()}
 * 只能静态声明能力的不足。
 * </p>
 * <p>
 * 实现示例：
 * <ul>
 *   <li>DeepSeekHealthChecker：通过扩展轮询通道查询 DS 标签页/登录状态</li>
 *   <li>ApiProviderHealthChecker：通过 ping API 端点检测可用性</li>
 * </ul>
 * </p>
 */
public interface ProviderHealthChecker {

    /**
     * 获取此检查器负责的 Provider ID
     */
    String getProviderId();

    /**
     * 执行健康检查（应快速返回，建议 &lt; 2s）
     */
    ProviderHealth check();
}
