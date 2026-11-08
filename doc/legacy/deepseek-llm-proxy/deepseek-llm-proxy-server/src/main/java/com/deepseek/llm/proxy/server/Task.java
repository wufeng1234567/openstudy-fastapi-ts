package com.deepseek.llm.proxy.server;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.enums.Phase;
import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import com.deepseek.llm.proxy.core.model.FullResponse;
import com.deepseek.llm.proxy.core.model.ToolCall;
import com.deepseek.llm.proxy.core.model.ToolResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;

/**
 * 单次 LLM 任务实体
 * <p>
 * 维护累积文本（thinking + response）、状态机、回调列表。
 * 一个任务对应一次 chat / ocr 调用。
 * </p>
 */
public class Task {

    private static final Logger log = LoggerFactory.getLogger(Task.class);

    private final String taskId;
    private final String providerId;
    private final String sessionId;
    private final String userId;
    private final long createdAtMs;
    private final long timeoutMs;

    private volatile Status status = Status.PENDING;
    private final StringBuilder thinkingText = new StringBuilder();
    private final StringBuilder responseText = new StringBuilder();
    private volatile Instant startedAt;
    private volatile Instant completedAt;
    private volatile ErrorCode errorCode;
    private volatile String errorMessage;

    /** SSE 推送回调列表（一个任务可被多个 SSE 订阅，例如多端同步） */
    private final List<Consumer<TaskEvent>> listeners = new ArrayList<>();

    /** 同步等待锁（chatSync 用） */
    private final CountDownLatch doneLatch = new CountDownLatch(1);

    /** 错误回调（用于 chatSync 失败时抓取异常） */
    private final AtomicReference<LlmProxyException> syncError = new AtomicReference<>();

    public Task(String taskId, String providerId, String sessionId, String userId, long timeoutMs) {
        this.taskId = taskId;
        this.providerId = providerId;
        this.sessionId = sessionId;
        this.userId = userId;
        this.timeoutMs = timeoutMs;
        this.createdAtMs = System.currentTimeMillis();
    }

    public String getTaskId() { return taskId; }
    public String getProviderId() { return providerId; }
    public String getSessionId() { return sessionId; }
    public String getUserId() { return userId; }
    public long getCreatedAtMs() { return createdAtMs; }
    public long getTimeoutMs() { return timeoutMs; }
    public Status getStatus() { return status; }
    public String getThinkingText() { return thinkingText.toString(); }
    public String getResponseText() { return responseText.toString(); }
    public Instant getStartedAt() { return startedAt; }
    public Instant getCompletedAt() { return completedAt; }
    public ErrorCode getErrorCode() { return errorCode; }
    public String getErrorMessage() { return errorMessage; }

    public boolean isDone() {
        return status == Status.COMPLETED || status == Status.ERROR || status == Status.CANCELLED;
    }

    public void addListener(Consumer<TaskEvent> listener) {
        listeners.add(listener);
    }

    /** 任务被扩展拉取（开始执行） */
    public void markRunning() {
        if (status != Status.PENDING) {
            log.warn("任务 {} 状态非 PENDING，无法 markRunning：{}", taskId, status);
            return;
        }
        status = Status.RUNNING;
        startedAt = Instant.now();
        emit(TaskEvent.running(taskId));
    }

    /** 扩展回传 chunk（累积全文模式，与 DS 插件保持一致） */
    public void pushChunk(String content, Phase phase) {
        if (isDone()) return;
        if (status == Status.PENDING) status = Status.RUNNING;
        if (startedAt == null) startedAt = Instant.now();

        String delta;
        if (phase == Phase.THINKING) {
            delta = computeDelta(thinkingText.toString(), content);
            thinkingText.setLength(0);
            thinkingText.append(content);
        } else {
            delta = computeDelta(responseText.toString(), content);
            responseText.setLength(0);
            responseText.append(content);
        }
        emit(TaskEvent.chunk(taskId, phase, delta, content));
    }

    /** 工具调用（Agent 模式） */
    public void pushToolCall(ToolCall call) {
        emit(TaskEvent.toolCall(taskId, call));
    }

    /** 工具结果 */
    public void pushToolResult(ToolResult result) {
        emit(TaskEvent.toolResult(taskId, result));
    }

    /** 任务完成 */
    public void pushDone() {
        if (isDone()) return;
        status = Status.COMPLETED;
        completedAt = Instant.now();
        FullResponse full = new FullResponse();
        full.setRequestId(taskId);
        full.setSessionId(sessionId);
        full.setProviderId(providerId);
        full.setContent(responseText.toString());
        full.setThinkingContent(thinkingText.toString());
        full.setCompletedAt(completedAt);
        emit(TaskEvent.complete(taskId, full));
        doneLatch.countDown();
    }

    /** 任务错误 */
    public void pushError(ErrorCode code, String message) {
        if (isDone()) return;
        status = Status.ERROR;
        completedAt = Instant.now();
        this.errorCode = code;
        this.errorMessage = message;
        LlmProxyException ex = new LlmProxyException(code, message);
        syncError.set(ex);
        emit(TaskEvent.error(taskId, ex));
        doneLatch.countDown();
    }

    /** 任务取消 */
    public void pushCancelled() {
        if (isDone()) return;
        status = Status.CANCELLED;
        completedAt = Instant.now();
        emit(TaskEvent.cancelled(taskId));
        doneLatch.countDown();
    }

    /** 同步等待任务完成（chatSync 用） */
    public FullResponse awaitSync() throws LlmProxyException, InterruptedException {
        long remainMs = timeoutMs - (System.currentTimeMillis() - createdAtMs);
        if (remainMs <= 0) {
            throw new LlmProxyException(ErrorCode.TASK_TIMEOUT, "任务等待超时：" + taskId);
        }
        if (!doneLatch.await(remainMs, TimeUnit.MILLISECONDS)) {
            throw new LlmProxyException(ErrorCode.TASK_TIMEOUT, "任务等待超时：" + taskId);
        }
        LlmProxyException ex = syncError.get();
        if (ex != null) throw ex;
        if (status == Status.CANCELLED) {
            throw new LlmProxyException(ErrorCode.TASK_CANCELLED, "任务已取消：" + taskId);
        }
        FullResponse resp = new FullResponse();
        resp.setRequestId(taskId);
        resp.setSessionId(sessionId);
        resp.setProviderId(providerId);
        resp.setContent(responseText.toString());
        resp.setThinkingContent(thinkingText.toString());
        resp.setCompletedAt(completedAt);
        return resp;
    }

    private String computeDelta(String prev, String current) {
        if (current == null) return "";
        if (prev == null || prev.isEmpty()) return current;
        if (current.startsWith(prev)) {
            return current.substring(prev.length());
        }
        // 非累积模式：直接返回 current 作为增量
        return current;
    }

    private void emit(TaskEvent event) {
        for (Consumer<TaskEvent> listener : listeners) {
            try {
                listener.accept(event);
            } catch (Exception e) {
                log.warn("任务事件监听器异常：{}", e.getMessage());
            }
        }
    }

    /** 任务状态机 */
    public enum Status {
        PENDING,    // 已入队，等待扩展拉取
        RUNNING,    // 扩展已拉取，正在执行
        COMPLETED,  // 正常完成
        ERROR,      // 错误终止
        CANCELLED   // 被取消
    }
}
