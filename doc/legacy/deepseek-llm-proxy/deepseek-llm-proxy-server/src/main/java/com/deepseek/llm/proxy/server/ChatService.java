package com.deepseek.llm.proxy.server;

import com.deepseek.llm.proxy.core.BrowserExtensionProvider;
import com.deepseek.llm.proxy.core.LlmProvider;
import com.deepseek.llm.proxy.core.callback.StreamCallback;
import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.enums.Phase;
import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import com.deepseek.llm.proxy.core.model.ChatRequest;
import com.deepseek.llm.proxy.core.model.ChatResponse;
import com.deepseek.llm.proxy.core.model.FullResponse;
import com.deepseek.llm.proxy.core.model.HistoryMessage;
import com.deepseek.llm.proxy.core.model.TaskPayload;
import com.deepseek.llm.proxy.core.prompt.PromptManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * Chat 业务服务
 * <p>
 * 负责：
 * <ul>
 *   <li>校验请求 + 选择 Provider</li>
 *   <li>解析 promptId / systemPrompt / history 拼装最终 content（DS 网页版无 system role）</li>
 *   <li>enableMemory=true 时自动加载历史 + 完成后保存新消息</li>
 *   <li>创建 Task 入队，注册 StreamCallback 桥接</li>
 *   <li>同步调用 awaitSync 阻塞返回</li>
 * </ul>
 * </p>
 */
public class ChatService {

    private static final Logger log = LoggerFactory.getLogger(ChatService.class);

    private final TaskManager taskManager;
    private final ProviderRegistry providerRegistry;
    private final long defaultTimeoutMs;
    /** 可选，未配置时 promptId 字段被忽略，回退到 systemPrompt */
    private final PromptManager promptManager;
    /** 默认 chat 提示词 ID（未指定 promptId 也未指定 systemPrompt 时使用；null 表示不使用默认） */
    private final String defaultChatPromptId;
    /** 可选，未配置时不启用记忆功能（enableMemory 字段被忽略） */
    private final ConversationService conversationService;

    public ChatService(TaskManager taskManager, ProviderRegistry providerRegistry, long defaultTimeoutMs) {
        this(taskManager, providerRegistry, defaultTimeoutMs, null, null, null);
    }

    public ChatService(TaskManager taskManager, ProviderRegistry providerRegistry, long defaultTimeoutMs,
                       PromptManager promptManager, String defaultChatPromptId) {
        this(taskManager, providerRegistry, defaultTimeoutMs, promptManager, defaultChatPromptId, null);
    }

    public ChatService(TaskManager taskManager, ProviderRegistry providerRegistry, long defaultTimeoutMs,
                       PromptManager promptManager, String defaultChatPromptId,
                       ConversationService conversationService) {
        this.taskManager = taskManager;
        this.providerRegistry = providerRegistry;
        this.defaultTimeoutMs = defaultTimeoutMs;
        this.promptManager = promptManager;
        this.defaultChatPromptId = defaultChatPromptId;
        this.conversationService = conversationService;
    }

    /** 流式 chat：返回 taskId，结果通过 callback 异步回传 */
    public String chat(ChatRequest request, StreamCallback callback) throws LlmProxyException {
        validateRequest(request);

        LlmProvider provider = providerRegistry.require(request.getProviderId());
        if (!provider.supportsStreaming()) {
            throw new LlmProxyException(ErrorCode.UNSUPPORTED_FEATURE,
                    "Provider " + provider.getId() + " 不支持流式输出");
        }

        // 记忆集成：enableMemory=true 时自动加载历史 + ensureSession
        MemoryContext memCtx = prepareMemoryContext(request);

        String taskId = "task-" + UUID.randomUUID().toString();
        long timeoutMs = request.getTimeoutMs() != null ? request.getTimeoutMs() : defaultTimeoutMs;
        Task task = new Task(taskId, provider.getId(), request.getSessionId(), request.getUserId(), timeoutMs);

        // 包装 callback：在 onComplete 时保存消息到会话
        StreamCallback wrappedCallback = wrapCallbackForMemory(callback, request, memCtx);

        // 注册 listener → StreamCallback 桥接
        task.addListener(event -> dispatchToCallback(event, wrappedCallback));

        // 序列化为扩展任务载荷并提交
        TaskPayload payload = serializeTask(taskId, request, provider);
        taskManager.submit(task);

        log.info("chat 任务已提交：taskId={}, provider={}, memory={}", taskId, provider.getId(), memCtx.enabled);
        return taskId;
    }

    /** 同步 chat：阻塞至完成 */
    public ChatResponse chatSync(ChatRequest request) throws LlmProxyException {
        validateRequest(request);
        LlmProvider provider = providerRegistry.require(request.getProviderId());

        // 记忆集成
        MemoryContext memCtx = prepareMemoryContext(request);

        String taskId = "task-" + UUID.randomUUID().toString();
        long timeoutMs = request.getTimeoutMs() != null ? request.getTimeoutMs() : defaultTimeoutMs;
        Task task = new Task(taskId, provider.getId(), request.getSessionId(), request.getUserId(), timeoutMs);

        taskManager.submit(task);

        try {
            FullResponse full = task.awaitSync();
            ChatResponse resp = new ChatResponse();
            resp.setRequestId(full.getRequestId());
            resp.setSessionId(full.getSessionId());
            resp.setProviderId(full.getProviderId());
            resp.setContent(full.getContent());
            resp.setThinkingContent(full.getThinkingContent());
            resp.setCompletedAt(full.getCompletedAt());

            // 同步调用：完成后保存消息
            persistConversation(request, memCtx, full.getContent(), full.getThinkingContent());

            return resp;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new LlmProxyException(ErrorCode.INTERNAL_ERROR, "同步等待被中断", e);
        }
    }

    /** 扩展回传 chunk 时调用 */
    public void onChunk(String taskId, String content, Phase phase) throws LlmProxyException {
        Task task = taskManager.find(taskId).orElse(null);
        // 任务已结束/不存在时静默返回：扩展端可能在网络抖动后重试 chunk/done，
        // 任务此时已被 markCompleted 清理，抛异常会导致日志刷屏 + 触发 GlobalExceptionHandler
        if (task == null) {
            log.debug("onChunk: 任务不存在（可能已完成）：taskId={}", taskId);
            return;
        }
        task.pushChunk(content, phase);
    }

    /** 扩展回传完成 */
    public void onDone(String taskId) throws LlmProxyException {
        Task task = taskManager.find(taskId).orElse(null);
        // 任务不存在时静默返回：扩展端收到首次 done 响应后若重试，任务已被 markCompleted 清理
        if (task == null) {
            log.debug("onDone: 任务不存在（可能已完成）：taskId={}", taskId);
            return;
        }
        task.pushDone();
        taskManager.markCompleted(taskId);
    }

    /** 扩展回传错误 */
    public void onError(String taskId, ErrorCode code, String message) {
        // 任务不存在时静默：扩展端可能在重试 error 上报，任务已被清理
        if (taskManager.find(taskId).isEmpty()) {
            log.debug("onError: 任务不存在（可能已完成）：taskId={}, code={}, msg={}", taskId, code, message);
            return;
        }
        taskManager.markError(taskId, code, message);
    }

    private void validateRequest(ChatRequest request) throws LlmProxyException {
        if (request == null) {
            throw new LlmProxyException(ErrorCode.INVALID_REQUEST, "request 不能为空");
        }
        if (request.getProviderId() == null || request.getProviderId().isEmpty()) {
            throw new LlmProxyException(ErrorCode.INVALID_REQUEST, "providerId 不能为空");
        }
        if (request.getContent() == null || request.getContent().isEmpty()) {
            throw new LlmProxyException(ErrorCode.INVALID_REQUEST, "content 不能为空");
        }
    }

    // ========== 记忆集成 ==========

    /** 记忆上下文（prepareMemoryContext 的返回值） */
    private static class MemoryContext {
        boolean enabled = false;
        String sessionId = null;
        /** 自动加载的历史是否被合并到了 request.history */
        boolean historyMerged = false;

        /** 用户消息是否已保存（避免重复保存） */
        boolean userMessageSaved = false;
    }

    /**
     * 准备记忆上下文：
     * <ul>
     *   <li>enableMemory=true 且 sessionId 非空 且 ConversationService 可用 → 启用记忆</li>
     *   <li>启用记忆时：ensureSession（不存在则创建）+ 加载历史合并到 request.history</li>
     *   <li>启用记忆时：立即保存 user 消息</li>
     * </ul>
     */
    private MemoryContext prepareMemoryContext(ChatRequest request) throws LlmProxyException {
        MemoryContext ctx = new MemoryContext();
        if (conversationService == null) {
            return ctx;
        }
        Boolean enableMemory = request.getEnableMemory();
        if (enableMemory == null || !enableMemory) {
            return ctx;
        }
        if (request.getUserId() == null || request.getUserId().isEmpty()) {
            log.debug("enableMemory=true 但 userId 为空，跳过记忆功能");
            return ctx;
        }

        // sessionId 为空时自动创建
        String sessionId = request.getSessionId();
        if (sessionId == null || sessionId.isEmpty()) {
            sessionId = conversationService.createSession(
                    request.getUserId(), request.getProviderId(),
                    request.getTenantId(), null);
            request.setSessionId(sessionId);
            log.info("记忆功能启用，自动创建会话: sessionId={}", sessionId);
        } else {
            // 归属权校验：防止用户 A 用自己的 userId 配合用户 B 的 sessionId 偷看历史
            conversationService.requireOwnership(sessionId, request.getUserId());
            // 确保 sessionId 存在（防伪造）
            sessionId = conversationService.ensureSession(
                    sessionId, request.getUserId(), request.getProviderId(), request.getTenantId());
            request.setSessionId(sessionId);
        }

        ctx.enabled = true;
        ctx.sessionId = sessionId;

        // 加载历史并合并到 request.history
        List<HistoryMessage> history = conversationService.loadHistory(sessionId);
        if (!history.isEmpty()) {
            List<HistoryMessage> merged = new ArrayList<>(history);
            if (request.getHistory() != null && !request.getHistory().isEmpty()) {
                // 调用方手动注入的 history 追加在自动加载的历史之后
                merged.addAll(request.getHistory());
            }
            request.setHistory(merged);
            ctx.historyMerged = true;
            log.debug("已加载 {} 条历史消息: sessionId={}", history.size(), sessionId);
        }

        // 立即保存用户消息（无论后续任务成功失败）
        conversationService.appendUserMessage(sessionId, request.getContent());
        ctx.userMessageSaved = true;

        return ctx;
    }

    /**
     * 包装 callback：在 onComplete 时保存 assistant 消息
     */
    private StreamCallback wrapCallbackForMemory(StreamCallback original, ChatRequest request, MemoryContext ctx) {
        if (!ctx.enabled || original == null) {
            return original;
        }
        return new StreamCallback() {
            @Override
            public void onChunk(String delta) {
                original.onChunk(delta);
            }

            @Override
            public void onThinking(String delta) {
                original.onThinking(delta);
            }

            @Override
            public void onComplete(com.deepseek.llm.proxy.core.model.FullResponse fullResponse) {
                // 先保存消息，再回调业务层
                persistConversation(request, ctx, fullResponse.getContent(), fullResponse.getThinkingContent());
                original.onComplete(fullResponse);
            }

            @Override
            public void onError(com.deepseek.llm.proxy.core.exception.LlmProxyException error) {
                // 错误时也保存一条 assistant 错误占位（可选）
                // 这里选择不保存，保持会话干净
                original.onError(error);
            }
        };
    }

    /**
     * 持久化 assistant 回复
     */
    private void persistConversation(ChatRequest request, MemoryContext ctx,
                                     String assistantContent, String thinkingContent) {
        if (!ctx.enabled || ctx.sessionId == null) {
            return;
        }
        if (assistantContent == null || assistantContent.isEmpty()) {
            log.debug("assistant 内容为空，跳过保存: sessionId={}", ctx.sessionId);
            return;
        }
        conversationService.appendAssistantMessage(ctx.sessionId, assistantContent, thinkingContent);
        log.debug("已保存 assistant 消息: sessionId={}, contentLen={}",
                ctx.sessionId, assistantContent.length());
    }

    // ========== 序列化与拼装 ==========

    /** 序列化为扩展任务载荷 */
    private TaskPayload serializeTask(String taskId, ChatRequest request, LlmProvider provider) {
        TaskPayload payload = new TaskPayload();
        payload.setTaskId(taskId);
        payload.setType("chat");

        // DS 网页版无 system role：把 systemPrompt + history 拼到 content 前面
        String fullContent = assembleContent(request);
        payload.setContent(fullContent);

        // 图片
        if (request.getImages() != null && !request.getImages().isEmpty()) {
            payload.setImages(request.getImages().stream()
                    .map(img -> img.getDataUrl())
                    .toList());
        }

        // 文件
        if (request.getFiles() != null && !request.getFiles().isEmpty()) {
            payload.setFiles(request.getFiles().stream()
                    .map(f -> {
                        java.util.Map<String, String> m = new java.util.HashMap<>();
                        m.put("name", f.getName());
                        m.put("dataUrl", f.getDataUrl());
                        m.put("mimeType", f.getMimeType());
                        return m;
                    })
                    .toList());
        }

        payload.setEnableThinking(request.getEnableThinking());
        payload.setMode(request.getMode());
        payload.setNewSession(request.getEnableMemory() == null ? null : !request.getEnableMemory());
        return payload;
    }

    /**
     * DS 网页版无 system role，把 promptId 渲染结果 / systemPrompt + history 拼到 content 前
     * <p>
     * 优先级：promptId &gt; systemPrompt &gt; defaultChatPromptId
     * </p>
     */
    private String assembleContent(ChatRequest request) {
        StringBuilder sb = new StringBuilder();

        // 1. 解析 systemPrompt 来源（promptId 渲染 > systemPrompt 字段 > defaultChatPromptId）
        String resolvedSystemPrompt = resolveSystemPrompt(request);
        if (resolvedSystemPrompt != null && !resolvedSystemPrompt.isEmpty()) {
            sb.append(resolvedSystemPrompt).append("\n\n");
        }

        // 2. 拼接历史对话
        if (request.getHistory() != null && !request.getHistory().isEmpty()) {
            sb.append("## 历史对话\n\n");
            for (HistoryMessage msg : request.getHistory()) {
                sb.append("**").append(msg.getRole()).append("**: ")
                  .append(msg.getContent() != null ? msg.getContent() : "")
                  .append("\n\n");
            }
        }

        // 3. 用户消息
        sb.append("## 用户消息\n\n").append(request.getContent());
        return sb.toString();
    }

    /**
     * 解析 systemPrompt：
     * <ol>
     *   <li>若 request.promptId 非空，通过 PromptManager 渲染（失败时降级到 systemPrompt）</li>
     *   <li>否则若 request.systemPrompt 非空，直接使用</li>
     *   <li>否则若 defaultChatPromptId 配置且 PromptManager 可用，渲染默认模板</li>
     *   <li>否则返回 null</li>
     * </ol>
     */
    private String resolveSystemPrompt(ChatRequest request) {
        // 1. promptId 优先
        if (request.getPromptId() != null && !request.getPromptId().isEmpty()) {
            if (promptManager == null) {
                log.warn("请求指定了 promptId={} 但 PromptManager 未配置，降级到 systemPrompt", request.getPromptId());
            } else {
                try {
                    return promptManager.render(request.getPromptId(), request.getPromptVariables());
                } catch (Exception e) {
                    log.warn("渲染提示词 promptId={} 失败，降级到 systemPrompt: {}", request.getPromptId(), e.getMessage());
                }
            }
        }

        // 2. systemPrompt 字段
        if (request.getSystemPrompt() != null && !request.getSystemPrompt().isEmpty()) {
            return request.getSystemPrompt();
        }

        // 3. 默认模板
        if (defaultChatPromptId != null && !defaultChatPromptId.isEmpty() && promptManager != null) {
            try {
                return promptManager.render(defaultChatPromptId, request.getPromptVariables());
            } catch (Exception e) {
                log.debug("默认 chat 提示词 {} 渲染失败: {}", defaultChatPromptId, e.getMessage());
            }
        }

        return null;
    }

    /** TaskEvent → StreamCallback 路由 */
    private void dispatchToCallback(TaskEvent event, StreamCallback callback) {
        if (callback == null) return;
        try {
            switch (event.getType()) {
                case CHUNK:
                    if (event.getPhase() == Phase.THINKING) {
                        callback.onThinking(event.getDelta());
                    } else {
                        callback.onChunk(event.getDelta());
                    }
                    break;
                case TOOL_CALL:
                    callback.onToolCall(event.getToolCall());
                    break;
                case TOOL_RESULT:
                    callback.onToolResult(event.getToolResult());
                    break;
                case COMPLETE:
                    callback.onComplete(event.getFullResponse());
                    break;
                case ERROR:
                    callback.onError(event.getError());
                    break;
                default:
                    // RUNNING / CANCELLED 不触发回调
            }
        } catch (Exception e) {
            log.warn("StreamCallback 回调异常：{}", e.getMessage());
        }
    }
}
