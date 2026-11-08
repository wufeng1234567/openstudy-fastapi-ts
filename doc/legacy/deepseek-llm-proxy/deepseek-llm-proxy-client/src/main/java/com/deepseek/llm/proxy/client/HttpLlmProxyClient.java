package com.deepseek.llm.proxy.client;

import com.deepseek.llm.proxy.core.callback.OcrCallback;
import com.deepseek.llm.proxy.core.callback.StreamCallback;
import com.deepseek.llm.proxy.core.enums.Capability;
import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.enums.Phase;
import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import com.deepseek.llm.proxy.core.model.ChatRequest;
import com.deepseek.llm.proxy.core.model.ChatResponse;
import com.deepseek.llm.proxy.core.model.FullResponse;
import com.deepseek.llm.proxy.core.model.OcrRequest;
import com.deepseek.llm.proxy.core.model.OcrResponse;
import com.deepseek.llm.proxy.core.model.ProviderInfo;
import com.deepseek.llm.proxy.core.model.ProxyStatus;
import com.deepseek.llm.proxy.core.model.ToolCall;
import com.deepseek.llm.proxy.core.model.ToolResult;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicReference;

/**
 * HTTP/SSE 客户端实现
 * <p>
 * 通过 HTTP POST 调用远端 LLM Proxy Server：
 * <ul>
 *   <li>chat → POST /api/v1/llm-proxy/chat（SSE 流）</li>
 *   <li>chatSync → POST /api/v1/llm-proxy/chat/sync</li>
 *   <li>ocr → POST /api/v1/llm-proxy/ocr（SSE 流）</li>
 *   <li>ocrSync → POST /api/v1/llm-proxy/ocr/sync</li>
 *   <li>cancel → DELETE /api/v1/llm-proxy/tasks/{requestId}</li>
 *   <li>status → GET /api/v1/llm-proxy/status</li>
 *   <li>providers → GET /api/v1/llm-proxy/providers</li>
 *   <li>capabilities → GET /api/v1/llm-proxy/providers/{id}/capabilities</li>
 * </ul>
 * </p>
 * <p>使用 JDK HttpURLConnection 实现，避免引入额外依赖。SSE 流通过 BufferedReader 逐行解析。</p>
 */
public class HttpLlmProxyClient implements com.deepseek.llm.proxy.core.LlmProxyClient {

    private static final Logger log = LoggerFactory.getLogger(HttpLlmProxyClient.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final String baseUrl;
    private final String token;
    private final int connectTimeoutMs;
    private final int readTimeoutMs;
    private final ConcurrentMap<String, Thread> runningTasks = new ConcurrentHashMap<>();

    public HttpLlmProxyClient(String baseUrl) {
        this(baseUrl, null, 10000, 600000);
    }

    public HttpLlmProxyClient(String baseUrl, String token, int connectTimeoutMs, int readTimeoutMs) {
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.token = token;
        this.connectTimeoutMs = connectTimeoutMs;
        this.readTimeoutMs = readTimeoutMs;
    }

    @Override
    public String chat(ChatRequest request, StreamCallback callback) throws LlmProxyException {
        String requestId = "client-" + UUID.randomUUID();
        Thread worker = new Thread(() -> {
            HttpURLConnection conn = null;
            try {
                conn = openConnection("/api/v1/llm-proxy/chat", "POST", "text/event-stream");
                writeJson(conn, request);
                int code = conn.getResponseCode();
                if (code != 200) {
                    String err = readAll(conn);
                    if (callback != null) {
                        callback.onError(new LlmProxyException(ErrorCode.PROVIDER_ERROR,
                                "HTTP " + code + ": " + err));
                    }
                    return;
                }
                // 解析 SSE 流
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                    String line;
                    String currentEvent = "message";
                    while ((line = reader.readLine()) != null) {
                        if (line.startsWith("event:")) {
                            currentEvent = line.substring(6).trim();
                        } else if (line.startsWith("data:")) {
                            String json = line.substring(5).trim();
                            handleSseEvent(currentEvent, json, callback);
                            currentEvent = "message";
                        } else if (line.isEmpty()) {
                            // 事件分隔
                        }
                    }
                }
            } catch (Exception e) {
                if (callback != null) {
                    callback.onError(new LlmProxyException(ErrorCode.NETWORK_ERROR, e.getMessage(), e));
                }
            } finally {
                if (conn != null) conn.disconnect();
                runningTasks.remove(requestId);
            }
        }, "HttpLlmProxy-Chat-" + requestId);
        worker.setDaemon(true);
        worker.start();
        runningTasks.put(requestId, worker);
        return requestId;
    }

    @Override
    public ChatResponse chatSync(ChatRequest request) throws LlmProxyException {
        try {
            HttpURLConnection conn = openConnection("/api/v1/llm-proxy/chat/sync", "POST", "application/json");
            writeJson(conn, request);
            int code = conn.getResponseCode();
            String body = readAll(conn);
            if (code != 200) {
                throw new LlmProxyException(ErrorCode.PROVIDER_ERROR, "HTTP " + code + ": " + body);
            }
            return MAPPER.readValue(body, ChatResponse.class);
        } catch (LlmProxyException e) {
            throw e;
        } catch (Exception e) {
            throw new LlmProxyException(ErrorCode.NETWORK_ERROR, e.getMessage(), e);
        }
    }

    @Override
    public String ocr(OcrRequest request, OcrCallback callback) throws LlmProxyException {
        String requestId = "client-ocr-" + UUID.randomUUID();
        Thread t = new Thread(() -> {
            HttpURLConnection conn = null;
            try {
                conn = openConnection("/api/v1/llm-proxy/ocr", "POST", "text/event-stream");
                writeJson(conn, request);
                if (conn.getResponseCode() != 200) {
                    if (callback != null) {
                        callback.onError(new LlmProxyException(ErrorCode.PROVIDER_ERROR, readAll(conn)));
                    }
                    return;
                }
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                    String line;
                    String currentEvent = "message";
                    while ((line = reader.readLine()) != null) {
                        if (line.startsWith("event:")) {
                            currentEvent = line.substring(6).trim();
                        } else if (line.startsWith("data:")) {
                            String json = line.substring(5).trim();
                            handleOcrSseEvent(currentEvent, json, callback);
                            currentEvent = "message";
                        }
                    }
                }
            } catch (Exception e) {
                if (callback != null) {
                    callback.onError(new LlmProxyException(ErrorCode.NETWORK_ERROR, e.getMessage(), e));
                }
            } finally {
                if (conn != null) conn.disconnect();
            }
        }, "HttpLlmProxy-Ocr-" + requestId);
        t.setDaemon(true);
        t.start();
        return requestId;
    }

    @Override
    public OcrResponse ocrSync(OcrRequest request) throws LlmProxyException {
        try {
            HttpURLConnection conn = openConnection("/api/v1/llm-proxy/ocr/sync", "POST", "application/json");
            writeJson(conn, request);
            int code = conn.getResponseCode();
            String body = readAll(conn);
            if (code != 200) {
                throw new LlmProxyException(ErrorCode.PROVIDER_ERROR, "HTTP " + code + ": " + body);
            }
            return MAPPER.readValue(body, OcrResponse.class);
        } catch (LlmProxyException e) {
            throw e;
        } catch (Exception e) {
            throw new LlmProxyException(ErrorCode.NETWORK_ERROR, e.getMessage(), e);
        }
    }

    @Override
    public boolean cancel(String requestId) throws LlmProxyException {
        Thread worker = runningTasks.remove(requestId);
        if (worker != null) {
            worker.interrupt();
        }
        try {
            HttpURLConnection conn = openConnection("/api/v1/llm-proxy/tasks/" + requestId, "DELETE", null);
            int code = conn.getResponseCode();
            conn.disconnect();
            return code == 200;
        } catch (Exception e) {
            throw new LlmProxyException(ErrorCode.NETWORK_ERROR, e.getMessage(), e);
        }
    }

    @Override
    public ProxyStatus getStatus() throws LlmProxyException {
        try {
            HttpURLConnection conn = openConnection("/api/v1/llm-proxy/status", "GET", null);
            String body = readAll(conn);
            conn.disconnect();
            return MAPPER.readValue(body, ProxyStatus.class);
        } catch (Exception e) {
            throw new LlmProxyException(ErrorCode.NETWORK_ERROR, e.getMessage(), e);
        }
    }

    @Override
    public List<ProviderInfo> listProviders() throws LlmProxyException {
        try {
            HttpURLConnection conn = openConnection("/api/v1/llm-proxy/providers", "GET", null);
            String body = readAll(conn);
            conn.disconnect();
            return MAPPER.readValue(body,
                    MAPPER.getTypeFactory().constructCollectionType(List.class, ProviderInfo.class));
        } catch (Exception e) {
            throw new LlmProxyException(ErrorCode.NETWORK_ERROR, e.getMessage(), e);
        }
    }

    @Override
    public Set<Capability> getCapabilities(String providerId) throws LlmProxyException {
        try {
            HttpURLConnection conn = openConnection(
                    "/api/v1/llm-proxy/providers/" + providerId + "/capabilities", "GET", null);
            String body = readAll(conn);
            conn.disconnect();
            return MAPPER.readValue(body,
                    MAPPER.getTypeFactory().constructCollectionType(Set.class, Capability.class));
        } catch (Exception e) {
            throw new LlmProxyException(ErrorCode.NETWORK_ERROR, e.getMessage(), e);
        }
    }

    // ===== 内部工具 =====

    private HttpURLConnection openConnection(String path, String method, String contentType) throws IOException {
        URL url = URI.create(baseUrl + path).toURL();
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod(method);
        conn.setConnectTimeout(connectTimeoutMs);
        conn.setReadTimeout(readTimeoutMs);
        if (contentType != null) {
            conn.setRequestProperty("Content-Type", contentType);
            conn.setRequestProperty("Accept", contentType.contains("event-stream") ? contentType : "application/json");
        }
        if (token != null && !token.isEmpty()) {
            conn.setRequestProperty("Authorization", "Bearer " + token);
        }
        if (!"GET".equals(method) && !"DELETE".equals(method)) {
            conn.setDoOutput(true);
        }
        return conn;
    }

    private void writeJson(HttpURLConnection conn, Object body) throws IOException {
        try (OutputStream os = conn.getOutputStream()) {
            os.write(MAPPER.writeValueAsString(body).getBytes(StandardCharsets.UTF_8));
        }
    }

    private String readAll(HttpURLConnection conn) throws IOException {
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                sb.append(line).append('\n');
            }
            return sb.toString();
        } catch (IOException e) {
            // 错误响应可能从 errorStream 读
            try (BufferedReader er = new BufferedReader(
                    new InputStreamReader(conn.getErrorStream(), StandardCharsets.UTF_8))) {
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = er.readLine()) != null) {
                    sb.append(line).append('\n');
                }
                return sb.toString();
            } catch (Exception ignored) {
                throw e;
            }
        }
    }

    @SuppressWarnings("unchecked")
    private void handleSseEvent(String event, String json, StreamCallback callback) throws Exception {
        if (callback == null) return;
        var data = MAPPER.readValue(json, java.util.Map.class);

        switch (event) {
            case "thinking":
                callback.onThinking((String) data.get("delta"));
                break;
            case "chunk":
                callback.onChunk((String) data.get("delta"));
                break;
            case "tool_call":
                callback.onToolCall(MAPPER.convertValue(data, ToolCall.class));
                break;
            case "tool_result":
                callback.onToolResult(MAPPER.convertValue(data, ToolResult.class));
                break;
            case "complete":
                FullResponse full = new FullResponse();
                full.setRequestId((String) data.get("requestId"));
                full.setContent((String) data.get("content"));
                full.setThinkingContent((String) data.get("thinkingContent"));
                String ts = (String) data.get("completedAt");
                if (ts != null) full.setCompletedAt(Instant.parse(ts));
                callback.onComplete(full);
                break;
            case "error":
                Integer code = (Integer) data.get("code");
                String name = (String) data.get("name");
                String msg = (String) data.get("message");
                ErrorCode ec = ErrorCode.INTERNAL_ERROR;
                if (code != null) {
                    for (ErrorCode e : ErrorCode.values()) {
                        if (e.getCode() == code) { ec = e; break; }
                    }
                }
                callback.onError(new LlmProxyException(ec, msg + " [" + name + "]"));
                break;
            default:
                log.debug("未知 SSE 事件：{} {}", event, json);
        }
    }

    @SuppressWarnings("unchecked")
    private void handleOcrSseEvent(String event, String json, OcrCallback callback) throws Exception {
        if (callback == null) return;
        var data = MAPPER.readValue(json, java.util.Map.class);
        switch (event) {
            case "chunk":
                callback.onChunk((String) data.get("delta"));
                break;
            case "complete":
                OcrResponse resp = new OcrResponse();
                resp.setRequestId((String) data.get("requestId"));
                resp.setText((String) data.get("text"));
                resp.setStructuredData(data.get("structuredData"));
                String ts = (String) data.get("completedAt");
                if (ts != null) resp.setCompletedAt(Instant.parse(ts));
                callback.onComplete(resp);
                break;
            case "error":
                Integer code = (Integer) data.get("code");
                String name = (String) data.get("name");
                String msg = (String) data.get("message");
                ErrorCode ec = ErrorCode.INTERNAL_ERROR;
                if (code != null) {
                    for (ErrorCode e : ErrorCode.values()) {
                        if (e.getCode() == code) { ec = e; break; }
                    }
                }
                callback.onError(new LlmProxyException(ec, msg + " [" + name + "]"));
                break;
            default:
                log.debug("未知 OCR SSE 事件：{} {}", event, json);
        }
    }
}
