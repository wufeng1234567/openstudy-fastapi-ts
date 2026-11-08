package com.deepseek.llm.proxy.core;

import com.deepseek.llm.proxy.core.callback.OcrCallback;
import com.deepseek.llm.proxy.core.callback.StreamCallback;
import com.deepseek.llm.proxy.core.enums.Capability;
import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import com.deepseek.llm.proxy.core.model.*;

import java.util.List;
import java.util.Set;

/**
 * LLM 代理客户端主接口（给其他系统调用）
 * <p>
 * 其他业务系统（电商、数据分析、客服等）通过此接口调用 LLM 能力，
 * 屏蔽底层 Provider 差异。
 * </p>
 * <p>
 * 实现类：
 * <ul>
 *   <li>HttpLlmProxyClient：HTTP/SSE 实现</li>
 *   <li>WebSocketLlmProxyClient：WebSocket 实现</li>
 *   <li>MockLlmProxyClient：Mock 实现（开发测试用）</li>
 * </ul>
 * </p>
 */
public interface LlmProxyClient {

    /**
     * 流式对话
     *
     * @param request  请求
     * @param callback 回调
     * @return requestId 用于后续 cancel
     */
    String chat(ChatRequest request, StreamCallback callback) throws LlmProxyException;

    /**
     * 同步阻塞对话
     */
    ChatResponse chatSync(ChatRequest request) throws LlmProxyException;

    /**
     * 流式 OCR
     */
    String ocr(OcrRequest request, OcrCallback callback) throws LlmProxyException;

    /**
     * 同步 OCR
     */
    OcrResponse ocrSync(OcrRequest request) throws LlmProxyException;

    /**
     * 取消任务
     *
     * @return true 取消成功 / false 任务已结束或不存在
     */
    boolean cancel(String requestId) throws LlmProxyException;

    /**
     * 服务状态
     */
    ProxyStatus getStatus() throws LlmProxyException;

    /**
     * Provider 列表
     */
    List<ProviderInfo> listProviders() throws LlmProxyException;

    /**
     * 能力探测
     */
    Set<Capability> getCapabilities(String providerId) throws LlmProxyException;
}
