package com.deepseek.llm.proxy.server;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.enums.Phase;
import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import com.deepseek.llm.proxy.core.model.TaskPayload;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/**
 * 扩展轮询通道 Controller
 * <p>
 * 浏览器扩展通过此通道与后端通信：
 * <ul>
 *   <li>GET /ext/poll：拉取待执行任务（长轮询 5s）</li>
 *   <li>POST /ext/{taskId}/chunk：回传流式 chunk</li>
 *   <li>POST /ext/{taskId}/done：回传完成</li>
 *   <li>POST /ext/{taskId}/error：回传错误</li>
 *   <li>GET /ext/status：查询扩展在线状态</li>
 * </ul>
 * </p>
 */
@RestController
@RequestMapping("/api/v1/llm-proxy/ext")
public class ExtensionPollController {

    private static final Logger log = LoggerFactory.getLogger(ExtensionPollController.class);
    private static final long POLL_TIMEOUT_MS = 5000L;

    private final TaskManager taskManager;
    private final ChatService chatService;
    private final ProviderRegistry providerRegistry;
    /** 扩展认证 token（null 表示不校验） */
    private final String extensionToken;

    @Autowired
    public ExtensionPollController(TaskManager taskManager,
                                   ChatService chatService,
                                   ProviderRegistry providerRegistry,
                                   org.springframework.core.env.Environment env) {
        this.taskManager = taskManager;
        this.chatService = chatService;
        this.providerRegistry = providerRegistry;
        this.extensionToken = env.getProperty("deepseek.llm-proxy.extension.token");
    }

    /** 拉取任务（长轮询 5s） */
    @GetMapping("/poll")
    public Map<String, Object> poll(
            @RequestHeader(value = "X-LLM-Proxy-Ext-Token", required = false) String token,
            @RequestParam(required = false) String tokenQuery) throws LlmProxyException {
        verifyToken(token, tokenQuery);
        try {
            Optional<Task> opt = taskManager.poll(POLL_TIMEOUT_MS);
            if (opt.isEmpty()) {
                return Map.of("hasTask", false);
            }
            Task task = opt.get();
            // 序列化为扩展载荷（与 BrowserExtensionProvider.serializeTask 对齐）
            Map<String, Object> taskData = new LinkedHashMap<>();
            taskData.put("hasTask", true);
            taskData.put("taskId", task.getTaskId());
            taskData.put("providerId", task.getProviderId());
            // 实际内容应由 ProviderRegistry → BrowserExtensionProvider.serializeTask 生成
            // 这里返回 task 元信息，由扩展根据 providerId 拉取对应序列化器
            taskData.put("sessionId", task.getSessionId());
            taskData.put("userId", task.getUserId());
            taskData.put("timeoutMs", task.getTimeoutMs());
            return taskData;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return Map.of("hasTask", false);
        }
    }

    /** 回传 chunk */
    @PostMapping("/{taskId}/chunk")
    public Map<String, Object> chunk(
            @PathVariable String taskId,
            @RequestBody ChunkRequest body,
            @RequestHeader(value = "X-LLM-Proxy-Ext-Token", required = false) String token,
            @RequestParam(required = false) String tokenQuery) throws LlmProxyException {
        verifyToken(token, tokenQuery);
        Phase phase = parsePhase(body.getPhase());
        chatService.onChunk(taskId, body.getContent(), phase);
        return Map.of("ok", true);
    }

    /** 回传完成 */
    @PostMapping("/{taskId}/done")
    public Map<String, Object> done(
            @PathVariable String taskId,
            @RequestHeader(value = "X-LLM-Proxy-Ext-Token", required = false) String token,
            @RequestParam(required = false) String tokenQuery) throws LlmProxyException {
        verifyToken(token, tokenQuery);
        chatService.onDone(taskId);
        return Map.of("ok", true);
    }

    /** 回传错误 */
    @PostMapping("/{taskId}/error")
    public Map<String, Object> error(
            @PathVariable String taskId,
            @RequestBody ErrorRequest body,
            @RequestHeader(value = "X-LLM-Proxy-Ext-Token", required = false) String token,
            @RequestParam(required = false) String tokenQuery) throws LlmProxyException {
        verifyToken(token, tokenQuery);
        ErrorCode code = parseErrorCode(body.getCode());
        chatService.onError(taskId, code, body.getMessage());
        return Map.of("ok", true);
    }

    /** 扩展在线状态 */
    @GetMapping("/status")
    public Map<String, Object> status() {
        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("online", taskManager.isExtensionOnline());
        resp.put("providers", providerRegistry.listIds());
        resp.put("queueSize", taskManager.getActiveCount());
        // 包含扩展最近上报的健康状态
        Map<String, Object> healthReport = taskManager.getExtensionHealthReport();
        if (healthReport != null) {
            resp.put("healthReport", healthReport);
            resp.put("healthReportAge", System.currentTimeMillis() - taskManager.getExtensionHealthReportTime());
        } else {
            resp.put("healthReport", null);
            resp.put("healthReportAge", -1);
        }
        return resp;
    }

    /**
     * 扩展主动上报健康状态
     * <p>POST /api/v1/llm-proxy/ext/health</p>
     * <p>Body: {"providerId": "deepseek-free", "dsTabOpen": true, "loggedIn": true, ...}</p>
     * <p>建议扩展每 30s 上报一次</p>
     */
    @PostMapping("/health")
    public Map<String, Object> reportHealth(
            @RequestBody Map<String, Object> body,
            @RequestHeader(value = "X-LLM-Proxy-Ext-Token", required = false) String token,
            @RequestParam(required = false) String tokenQuery) throws LlmProxyException {
        verifyToken(token, tokenQuery);
        taskManager.reportExtensionHealth(body);
        log.debug("扩展健康上报: {}", body);
        return Map.of("ok", true, "receivedAt", System.currentTimeMillis());
    }

    private void verifyToken(String headerToken, String queryToken) throws LlmProxyException {
        if (extensionToken == null || extensionToken.isEmpty()) return;
        String got = headerToken != null ? headerToken : queryToken;
        if (got == null || !extensionToken.equals(got)) {
            throw new LlmProxyException(ErrorCode.AUTH_FAILED, "扩展 token 校验失败");
        }
    }

    private Phase parsePhase(String phase) throws LlmProxyException {
        if (phase == null) return Phase.RESPONSE;
        switch (phase.toLowerCase()) {
            case "thinking": return Phase.THINKING;
            case "response": return Phase.RESPONSE;
            case "tool_call": return Phase.TOOL_CALL;
            case "tool_result": return Phase.TOOL_RESULT;
            default:
                throw new LlmProxyException(ErrorCode.INVALID_REQUEST, "未知 phase：" + phase);
        }
    }

    private ErrorCode parseErrorCode(Integer code) {
        if (code == null) return ErrorCode.PROVIDER_ERROR;
        for (ErrorCode ec : ErrorCode.values()) {
            if (ec.getCode() == code) return ec;
        }
        return ErrorCode.PROVIDER_ERROR;
    }

    /** chunk 请求体 */
    public static class ChunkRequest {
        private String content;
        private String phase;
        public String getContent() { return content; }
        public void setContent(String content) { this.content = content; }
        public String getPhase() { return phase; }
        public void setPhase(String phase) { this.phase = phase; }
    }

    /** error 请求体 */
    public static class ErrorRequest {
        private Integer code;
        private String message;
        public Integer getCode() { return code; }
        public void setCode(Integer code) { this.code = code; }
        public String getMessage() { return message; }
        public void setMessage(String message) { this.message = message; }
    }
}
