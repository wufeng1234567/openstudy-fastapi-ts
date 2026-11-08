package com.deepseek.llm.proxy.client;

import com.deepseek.llm.proxy.core.LlmProxyClient;
import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.net.http.WebSocket.Listener;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * WebSocket 客户端实现（小程序场景）
 * <p>
 * 用于小程序等无法直接拦截 SSE 的客户端，通过 WebSocket 与服务端保持长连接：
 * <ul>
 *   <li>客户端 → 服务端：发送 ChatRequest JSON</li>
 *   <li>服务端 → 客户端：推送 thinking / chunk / complete / error 事件</li>
 * </ul>
 * </p>
 * <p>
 * <b>注意：</b>此实现为客户端单端，需要服务端配套的 WebSocketHandler 支持。
 * 阶段 2 仅提供客户端骨架，具体协议需与服务端 WebSocketHandler 对齐。
 * </p>
 */
public class WebSocketLlmProxyClient implements LlmProxyClient {

    private static final Logger log = LoggerFactory.getLogger(WebSocketLlmProxyClient.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final String wsUrl;
    private final String token;
    private final WebSocket ws;
    private final ConcurrentMap<String, com.deepseek.llm.proxy.core.callback.StreamCallback> streamCallbacks = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, com.deepseek.llm.proxy.core.callback.OcrCallback> ocrCallbacks = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, CompletableFuture<com.deepseek.llm.proxy.core.model.ChatResponse>> syncFutures = new ConcurrentHashMap<>();
    private final ConcurrentMap<String, CompletableFuture<com.deepseek.llm.proxy.core.model.OcrResponse>> ocrSyncFutures = new ConcurrentHashMap<>();

    public WebSocketLlmProxyClient(String wsUrl, String token) {
        this.wsUrl = wsUrl;
        this.token = token;
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
        WebSocket.Builder b = client.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(10));
        if (token != null && !token.isEmpty()) {
            b.header("Authorization", "Bearer " + token);
        }
        this.ws = b.buildAsync(URI.create(wsUrl), new WsListener()).join();
        log.info("WebSocket 连接已建立：{}", wsUrl);
    }

    @Override
    public String chat(com.deepseek.llm.proxy.core.model.ChatRequest request,
                       com.deepseek.llm.proxy.core.callback.StreamCallback callback) throws LlmProxyException {
        String requestId = "ws-" + UUID.randomUUID();
        if (callback != null) streamCallbacks.put(requestId, callback);
        try {
            String json = MAPPER.writeValueAsString(new WsRequest("chat", requestId, request));
            ws.sendText(json, true);
        } catch (Exception e) {
            throw new LlmProxyException(ErrorCode.SERIALIZATION_ERROR, e.getMessage(), e);
        }
        return requestId;
    }

    @Override
    public com.deepseek.llm.proxy.core.model.ChatResponse chatSync(
            com.deepseek.llm.proxy.core.model.ChatRequest request) throws LlmProxyException {
        String requestId = "ws-sync-" + UUID.randomUUID();
        CompletableFuture<com.deepseek.llm.proxy.core.model.ChatResponse> future = new CompletableFuture<>();
        syncFutures.put(requestId, future);
        try {
            String json = MAPPER.writeValueAsString(new WsRequest("chatSync", requestId, request));
            ws.sendText(json, true);
        } catch (Exception e) {
            syncFutures.remove(requestId);
            throw new LlmProxyException(ErrorCode.SERIALIZATION_ERROR, e.getMessage(), e);
        }
        try {
            return future.get(request.getTimeoutMs() != null ? request.getTimeoutMs() : 300000L, TimeUnit.MILLISECONDS);
        } catch (Exception e) {
            syncFutures.remove(requestId);
            throw new LlmProxyException(ErrorCode.TASK_TIMEOUT, "WebSocket 同步等待超时", e);
        }
    }

    @Override
    public String ocr(com.deepseek.llm.proxy.core.model.OcrRequest request,
                      com.deepseek.llm.proxy.core.callback.OcrCallback callback) throws LlmProxyException {
        String requestId = "ws-ocr-" + UUID.randomUUID();
        if (callback != null) ocrCallbacks.put(requestId, callback);
        try {
            String json = MAPPER.writeValueAsString(new WsRequest("ocr", requestId, request));
            ws.sendText(json, true);
        } catch (Exception e) {
            throw new LlmProxyException(ErrorCode.SERIALIZATION_ERROR, e.getMessage(), e);
        }
        return requestId;
    }

    @Override
    public com.deepseek.llm.proxy.core.model.OcrResponse ocrSync(
            com.deepseek.llm.proxy.core.model.OcrRequest request) throws LlmProxyException {
        String requestId = "ws-ocr-sync-" + UUID.randomUUID();
        CompletableFuture<com.deepseek.llm.proxy.core.model.OcrResponse> future = new CompletableFuture<>();
        ocrSyncFutures.put(requestId, future);
        try {
            String json = MAPPER.writeValueAsString(new WsRequest("ocrSync", requestId, request));
            ws.sendText(json, true);
        } catch (Exception e) {
            ocrSyncFutures.remove(requestId);
            throw new LlmProxyException(ErrorCode.SERIALIZATION_ERROR, e.getMessage(), e);
        }
        try {
            return future.get(request.getTimeoutMs() != null ? request.getTimeoutMs() : 180000L, TimeUnit.MILLISECONDS);
        } catch (Exception e) {
            ocrSyncFutures.remove(requestId);
            throw new LlmProxyException(ErrorCode.TASK_TIMEOUT, "WebSocket OCR 同步等待超时", e);
        }
    }

    @Override
    public boolean cancel(String requestId) throws LlmProxyException {
        try {
            String json = MAPPER.writeValueAsString(new WsRequest("cancel", requestId, null));
            ws.sendText(json, true);
            streamCallbacks.remove(requestId);
            ocrCallbacks.remove(requestId);
            syncFutures.remove(requestId);
            ocrSyncFutures.remove(requestId);
            return true;
        } catch (Exception e) {
            throw new LlmProxyException(ErrorCode.SERIALIZATION_ERROR, e.getMessage(), e);
        }
    }

    @Override
    public com.deepseek.llm.proxy.core.model.ProxyStatus getStatus() throws LlmProxyException {
        // 简化：直接返回本地状态
        com.deepseek.llm.proxy.core.model.ProxyStatus s = new com.deepseek.llm.proxy.core.model.ProxyStatus();
        s.setAvailable(!ws.isOutputClosed());
        s.setOnlineProviders(0);
        s.setActiveTasks(streamCallbacks.size() + ocrCallbacks.size());
        s.setApiVersion("v1-ws");
        return s;
    }

    @Override
    public java.util.List<com.deepseek.llm.proxy.core.model.ProviderInfo> listProviders() throws LlmProxyException {
        // WebSocket 模式下不维护 provider 列表
        return java.util.List.of();
    }

    @Override
    public java.util.Set<com.deepseek.llm.proxy.core.enums.Capability> getCapabilities(String providerId) throws LlmProxyException {
        return java.util.EnumSet.noneOf(com.deepseek.llm.proxy.core.enums.Capability.class);
    }

    /** 关闭连接 */
    public void close() {
        ws.sendClose(WebSocket.NORMAL_CLOSURE, "client close");
    }

    // ===== WebSocket 监听器 =====

    private class WsListener implements Listener {
        private final StringBuilder buffer = new StringBuilder();

        @Override
        public void onOpen(WebSocket webSocket) {
            log.info("WebSocket onOpen");
            webSocket.request(Long.MAX_VALUE);
        }

        @Override
        public CompletionStage<?> onText(WebSocket webSocket, CharSequence data, boolean last) {
            buffer.append(data);
            if (last) {
                String msg = buffer.toString();
                buffer.setLength(0);
                handleMessage(msg);
            }
            return null;
        }

        @Override
        public void onError(WebSocket webSocket, Throwable error) {
            log.error("WebSocket onError", error);
        }

        @Override
        public CompletionStage<?> onClose(WebSocket webSocket, int statusCode, String reason) {
            log.info("WebSocket onClose: {} {}", statusCode, reason);
            return null;
        }
    }

    @SuppressWarnings("unchecked")
    private void handleMessage(String msg) {
        try {
            var map = MAPPER.readValue(msg, java.util.Map.class);
            String type = (String) map.get("type");
            String requestId = (String) map.get("requestId");

            switch (type != null ? type : "") {
                case "thinking":
                    com.deepseek.llm.proxy.core.callback.StreamCallback sc = streamCallbacks.get(requestId);
                    if (sc != null) sc.onThinking((String) map.get("delta"));
                    break;
                case "chunk":
                    sc = streamCallbacks.get(requestId);
                    if (sc != null) sc.onChunk((String) map.get("delta"));
                    break;
                case "complete":
                    sc = streamCallbacks.get(requestId);
                    if (sc != null) {
                        com.deepseek.llm.proxy.core.model.FullResponse full = MAPPER.convertValue(
                                map.get("response"), com.deepseek.llm.proxy.core.model.FullResponse.class);
                        sc.onComplete(full);
                        streamCallbacks.remove(requestId);
                    }
                    var syncFuture = syncFutures.remove(requestId);
                    if (syncFuture != null) {
                        com.deepseek.llm.proxy.core.model.ChatResponse resp = MAPPER.convertValue(
                                map.get("response"), com.deepseek.llm.proxy.core.model.ChatResponse.class);
                        syncFuture.complete(resp);
                    }
                    break;
                case "error":
                    ErrorCode code = ErrorCode.INTERNAL_ERROR;
                    Integer codeInt = (Integer) map.get("code");
                    if (codeInt != null) {
                        for (ErrorCode e : ErrorCode.values()) {
                            if (e.getCode() == codeInt) { code = e; break; }
                        }
                    }
                    LlmProxyException ex = new LlmProxyException(code, (String) map.get("message"));
                    sc = streamCallbacks.remove(requestId);
                    if (sc != null) sc.onError(ex);
                    var sf = syncFutures.remove(requestId);
                    if (sf != null) sf.completeExceptionally(ex);
                    var ocb = ocrCallbacks.remove(requestId);
                    if (ocb != null) ocb.onError(ex);
                    var osf = ocrSyncFutures.remove(requestId);
                    if (osf != null) osf.completeExceptionally(ex);
                    break;
                case "ocr-complete":
                    var ocrCallback = ocrCallbacks.remove(requestId);
                    if (ocrCallback != null) {
                        com.deepseek.llm.proxy.core.model.OcrResponse resp = MAPPER.convertValue(
                                map.get("response"), com.deepseek.llm.proxy.core.model.OcrResponse.class);
                        ocrCallback.onComplete(resp);
                    }
                    var ocrFuture = ocrSyncFutures.remove(requestId);
                    if (ocrFuture != null) {
                        com.deepseek.llm.proxy.core.model.OcrResponse resp = MAPPER.convertValue(
                                map.get("response"), com.deepseek.llm.proxy.core.model.OcrResponse.class);
                        ocrFuture.complete(resp);
                    }
                    break;
                default:
                    log.debug("未知 WS 消息类型：{}", type);
            }
        } catch (Exception e) {
            log.warn("WS 消息处理异常：{}", e.getMessage());
        }
    }

    /** WS 请求包装 */
    private static class WsRequest {
        public String type;
        public String requestId;
        public Object payload;
        public WsRequest(String type, String requestId, Object payload) {
            this.type = type;
            this.requestId = requestId;
            this.payload = payload;
        }
    }
}
