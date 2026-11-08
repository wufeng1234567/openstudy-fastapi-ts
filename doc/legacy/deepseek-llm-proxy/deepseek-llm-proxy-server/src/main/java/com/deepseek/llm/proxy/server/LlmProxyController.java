package com.deepseek.llm.proxy.server;

import com.deepseek.llm.proxy.core.callback.StreamCallback;
import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import com.deepseek.llm.proxy.core.model.ChatRequest;
import com.deepseek.llm.proxy.core.model.ChatResponse;
import com.deepseek.llm.proxy.core.model.FullResponse;
import com.deepseek.llm.proxy.core.model.OcrRequest;
import com.deepseek.llm.proxy.core.model.OcrResponse;
import com.deepseek.llm.proxy.core.model.ProviderInfo;
import com.deepseek.llm.proxy.core.model.ProxyStatus;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * LLM Proxy REST Controller
 * <p>对应 docs/api-spec.md §6 的全部 REST 端点。</p>
 */
@RestController
@RequestMapping("/api/v1/llm-proxy")
public class LlmProxyController {

    private static final Logger log = LoggerFactory.getLogger(LlmProxyController.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final long SSE_TIMEOUT = 600_000L; // 10 分钟

    private final ChatService chatService;
    private final OcrService ocrService;
    private final TaskManager taskManager;
    private final ProviderRegistry providerRegistry;
    /** 同步 chat 调用的等待锁池（taskId → SseEmitter 用于流式端点） */
    private final Map<String, SseEmitter> sseEmitters = new ConcurrentHashMap<>();

    @Autowired
    public LlmProxyController(ChatService chatService,
                              OcrService ocrService,
                              TaskManager taskManager,
                              ProviderRegistry providerRegistry) {
        this.chatService = chatService;
        this.ocrService = ocrService;
        this.taskManager = taskManager;
        this.providerRegistry = providerRegistry;
    }

    /** 6.2 流式对话：SSE */
    @PostMapping(value = "/chat", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter chat(@RequestBody ChatRequest request) {
        SseEmitter emitter = new SseEmitter(SSE_TIMEOUT);
        StreamCallback callback = new StreamCallback() {
            @Override
            public void onThinking(String delta) {
                sendEvent(emitter, "thinking", Map.of(
                        "delta", delta,
                        "phase", "THINKING"));
            }

            @Override
            public void onChunk(String delta) {
                sendEvent(emitter, "chunk", Map.of(
                        "delta", delta,
                        "phase", "RESPONSE"));
            }

            @Override
            public void onComplete(FullResponse response) {
                Map<String, Object> data = new java.util.LinkedHashMap<>();
                data.put("requestId", response.getRequestId());
                data.put("content", response.getContent());
                data.put("thinkingContent", response.getThinkingContent());
                data.put("completedAt", response.getCompletedAt() != null
                        ? response.getCompletedAt().toString() : null);
                sendEvent(emitter, "complete", data);
                emitter.complete();
            }

            @Override
            public void onError(LlmProxyException e) {
                sendEvent(emitter, "error", Map.of(
                        "code", e.getErrorCode().getCode(),
                        "name", e.getErrorCode().getName(),
                        "message", e.getMessage()));
                emitter.complete();
            }
        };

        try {
            String taskId = chatService.chat(request, callback);
            sseEmitters.put(taskId, emitter);
            emitter.onCompletion(() -> sseEmitters.remove(taskId));
            emitter.onTimeout(() -> {
                sseEmitters.remove(taskId);
                emitter.complete();
            });
            emitter.onError(t -> sseEmitters.remove(taskId));
        } catch (LlmProxyException e) {
            sendEvent(emitter, "error", Map.of(
                    "code", e.getErrorCode().getCode(),
                    "name", e.getErrorCode().getName(),
                    "message", e.getMessage()));
            emitter.complete();
        }
        return emitter;
    }

    /** 6.3 同步对话 */
    @PostMapping("/chat/sync")
    public ChatResponse chatSync(@RequestBody ChatRequest request) throws LlmProxyException {
        return chatService.chatSync(request);
    }

    /** 6.4 流式 OCR：SSE */
    @PostMapping(value = "/ocr", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter ocr(@RequestBody OcrRequest request) {
        SseEmitter emitter = new SseEmitter(SSE_TIMEOUT);
        var callback = new com.deepseek.llm.proxy.core.callback.OcrCallback() {
            @Override
            public void onChunk(String delta) {
                sendEvent(emitter, "chunk", Map.of("delta", delta));
            }

            @Override
            public void onComplete(OcrResponse response) {
                Map<String, Object> data = new java.util.LinkedHashMap<>();
                data.put("requestId", response.getRequestId());
                data.put("text", response.getText());
                data.put("structuredData", response.getStructuredData());
                data.put("completedAt", response.getCompletedAt() != null
                        ? response.getCompletedAt().toString() : null);
                sendEvent(emitter, "complete", data);
                emitter.complete();
            }

            @Override
            public void onError(LlmProxyException e) {
                sendEvent(emitter, "error", Map.of(
                        "code", e.getErrorCode().getCode(),
                        "name", e.getErrorCode().getName(),
                        "message", e.getMessage()));
                emitter.complete();
            }
        };
        try {
            ocrService.ocr(request, callback);
        } catch (LlmProxyException e) {
            sendEvent(emitter, "error", Map.of(
                    "code", e.getErrorCode().getCode(),
                    "name", e.getErrorCode().getName(),
                    "message", e.getMessage()));
            emitter.complete();
        }
        return emitter;
    }

    /** 6.5 同步 OCR */
    @PostMapping("/ocr/sync")
    public OcrResponse ocrSync(@RequestBody OcrRequest request) throws LlmProxyException {
        return ocrService.ocrSync(request);
    }

    /** 6.6 取消任务 */
    @DeleteMapping("/tasks/{requestId}")
    public Map<String, Object> cancel(@PathVariable String requestId) {
        boolean ok = taskManager.cancel(requestId);
        return Map.of("cancelled", ok);
    }

    /** 6.7 服务状态 */
    @GetMapping("/status")
    public ProxyStatus status() {
        ProxyStatus s = new ProxyStatus();
        s.setAvailable(true);
        s.setOnlineProviders(providerRegistry.size());
        s.setActiveTasks(taskManager.getActiveCount());
        s.setLastHeartbeat(Instant.now());
        s.setApiVersion("v1");
        s.setExtensionStatus(Map.of(
                "connected", taskManager.isExtensionOnline(),
                "queueSize", taskManager.getActiveCount()));
        return s;
    }

    /** 6.8 Provider 列表 */
    @GetMapping("/providers")
    public List<ProviderInfo> listProviders() {
        return providerRegistry.listAll();
    }

    /** 6.9 能力探测 */
    @GetMapping("/providers/{providerId}/capabilities")
    public Set<com.deepseek.llm.proxy.core.enums.Capability> capabilities(
            @PathVariable String providerId) throws LlmProxyException {
        return providerRegistry.require(providerId).getCapabilities();
    }

    /**
     * 6.10 健康检查：单个 Provider
     * <p>GET /api/v1/llm-proxy/providers/{providerId}/health</p>
     * <p>返回 Provider 运行时可用性（扩展在线、DS 标签页、登录状态等）</p>
     */
    @GetMapping("/providers/{providerId}/health")
    public com.deepseek.llm.proxy.core.ProviderHealth health(
            @PathVariable String providerId) throws LlmProxyException {
        // 校验 Provider 已注册
        providerRegistry.require(providerId);
        return providerRegistry.checkHealth(providerId);
    }

    /**
     * 6.11 健康检查：所有 Provider
     * <p>GET /api/v1/llm-proxy/health</p>
     */
    @GetMapping("/health")
    public List<com.deepseek.llm.proxy.core.ProviderHealth> healthAll() {
        return providerRegistry.checkAllHealth();
    }

    private void sendEvent(SseEmitter emitter, String eventName, Object data) {
        try {
            String json = MAPPER.writeValueAsString(data);
            emitter.send(SseEmitter.event().name(eventName).data(json));
        } catch (Exception e) {
            log.warn("SSE 发送失败：event={}, err={}", eventName, e.getMessage());
        }
    }
}
