package com.deepseek.llm.proxy.client;

import com.deepseek.llm.proxy.core.callback.StreamCallback;
import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import com.deepseek.llm.proxy.core.model.ChatRequest;
import com.deepseek.llm.proxy.core.model.ChatResponse;
import com.deepseek.llm.proxy.core.model.FullResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Mock 客户端实现（开发测试用）
 * <p>
 * 不连接真实服务端，本地模拟流式输出：
 * <ul>
 *   <li>逐字符回显 content（带 50ms 延迟）</li>
 *   <li>若 enableThinking=true，先输出 3 段思考</li>
 *   <li>5 秒后回调 onComplete</li>
 * </ul>
 * </p>
 */
public class MockLlmProxyClient implements com.deepseek.llm.proxy.core.LlmProxyClient {

    private static final Logger log = LoggerFactory.getLogger(MockLlmProxyClient.class);
    private static final long CHUNK_DELAY_MS = 50L;

    private final ConcurrentMap<String, Thread> runningTasks = new ConcurrentHashMap<>();
    private final AtomicLong requestCounter = new AtomicLong(0);

    @Override
    public String chat(ChatRequest request, StreamCallback callback) throws LlmProxyException {
        String requestId = "mock-" + UUID.randomUUID();
        requestCounter.incrementAndGet();

        Thread worker = new Thread(() -> {
            try {
                if (callback != null) {
                    // 深度思考
                    if (Boolean.TRUE.equals(request.getEnableThinking()) && callback != null) {
                        String[] thinkingParts = {
                                "正在分析问题...",
                                "考虑可能的方案...",
                                "组织回复结构..."
                        };
                        for (String part : thinkingParts) {
                            callback.onThinking(part);
                            Thread.sleep(CHUNK_DELAY_MS);
                        }
                    }
                    // 正式回复（逐字输出）
                    String reply = "这是 Mock 客户端的回复。你刚才说：" + request.getContent();
                    for (int i = 0; i < reply.length(); i++) {
                        callback.onChunk(String.valueOf(reply.charAt(i)));
                        Thread.sleep(CHUNK_DELAY_MS / 5);
                    }
                    // 完成
                    FullResponse full = new FullResponse();
                    full.setRequestId(requestId);
                    full.setSessionId(request.getSessionId());
                    full.setProviderId(request.getProviderId());
                    full.setContent(reply);
                    full.setCompletedAt(Instant.now());
                    callback.onComplete(full);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                if (callback != null) {
                    callback.onError(new LlmProxyException(ErrorCode.TASK_CANCELLED, "Mock 任务被中断"));
                }
            } catch (Exception e) {
                if (callback != null) {
                    callback.onError(new LlmProxyException(ErrorCode.INTERNAL_ERROR, e.getMessage(), e));
                }
            } finally {
                runningTasks.remove(requestId);
            }
        }, "MockChat-" + requestId);
        worker.setDaemon(true);
        worker.start();
        runningTasks.put(requestId, worker);
        log.info("Mock chat 任务启动：requestId={}", requestId);
        return requestId;
    }

    @Override
    public ChatResponse chatSync(ChatRequest request) throws LlmProxyException {
        String reply = "这是 Mock 客户端的同步回复。你刚才说：" + request.getContent();
        ChatResponse resp = new ChatResponse();
        resp.setRequestId("mock-sync-" + UUID.randomUUID());
        resp.setSessionId(request.getSessionId());
        resp.setProviderId(request.getProviderId());
        resp.setContent(reply);
        resp.setCompletedAt(Instant.now());
        return resp;
    }

    @Override
    public String ocr(com.deepseek.llm.proxy.core.model.OcrRequest request,
                      com.deepseek.llm.proxy.core.callback.OcrCallback callback) throws LlmProxyException {
        String requestId = "mock-ocr-" + UUID.randomUUID();
        Thread t = new Thread(() -> {
            try {
                if (callback != null) {
                    callback.onChunk("Mock OCR 结果：");
                    com.deepseek.llm.proxy.core.model.OcrResponse resp = new com.deepseek.llm.proxy.core.model.OcrResponse();
                    resp.setRequestId(requestId);
                    resp.setText("Mock OCR 提取的文本内容");
                    resp.setCompletedAt(Instant.now());
                    callback.onComplete(resp);
                }
            } catch (Exception e) {
                if (callback != null) {
                    callback.onError(new LlmProxyException(ErrorCode.INTERNAL_ERROR, e.getMessage(), e));
                }
            }
        }, "MockOcr-" + requestId);
        t.setDaemon(true);
        t.start();
        return requestId;
    }

    @Override
    public com.deepseek.llm.proxy.core.model.OcrResponse ocrSync(
            com.deepseek.llm.proxy.core.model.OcrRequest request) throws LlmProxyException {
        com.deepseek.llm.proxy.core.model.OcrResponse resp = new com.deepseek.llm.proxy.core.model.OcrResponse();
        resp.setRequestId("mock-ocr-sync-" + UUID.randomUUID());
        resp.setText("Mock OCR 同步结果");
        resp.setCompletedAt(Instant.now());
        return resp;
    }

    @Override
    public boolean cancel(String requestId) throws LlmProxyException {
        Thread worker = runningTasks.remove(requestId);
        if (worker != null) {
            worker.interrupt();
            return true;
        }
        return false;
    }

    @Override
    public com.deepseek.llm.proxy.core.model.ProxyStatus getStatus() throws LlmProxyException {
        com.deepseek.llm.proxy.core.model.ProxyStatus s = new com.deepseek.llm.proxy.core.model.ProxyStatus();
        s.setAvailable(true);
        s.setOnlineProviders(1);
        s.setActiveTasks(runningTasks.size());
        s.setLastHeartbeat(Instant.now());
        s.setApiVersion("v1-mock");
        s.setExtensionStatus(java.util.Map.of("mock", true));
        return s;
    }

    @Override
    public java.util.List<com.deepseek.llm.proxy.core.model.ProviderInfo> listProviders() throws LlmProxyException {
        com.deepseek.llm.proxy.core.model.ProviderInfo info = new com.deepseek.llm.proxy.core.model.ProviderInfo();
        info.setId("mock-provider");
        info.setDisplayName("Mock Provider");
        info.setCapabilities(java.util.EnumSet.of(
                com.deepseek.llm.proxy.core.enums.Capability.STREAMING,
                com.deepseek.llm.proxy.core.enums.Capability.THINKING,
                com.deepseek.llm.proxy.core.enums.Capability.IMAGES,
                com.deepseek.llm.proxy.core.enums.Capability.MEMORY));
        info.setSupportedModes(java.util.List.of(com.deepseek.llm.proxy.core.enums.ProviderMode.DEFAULT));
        info.setOnline(true);
        return java.util.List.of(info);
    }

    @Override
    public java.util.Set<com.deepseek.llm.proxy.core.enums.Capability> getCapabilities(String providerId) throws LlmProxyException {
        return java.util.EnumSet.of(
                com.deepseek.llm.proxy.core.enums.Capability.STREAMING,
                com.deepseek.llm.proxy.core.enums.Capability.THINKING,
                com.deepseek.llm.proxy.core.enums.Capability.IMAGES,
                com.deepseek.llm.proxy.core.enums.Capability.MEMORY);
    }
}
