package com.deepseek.llm.proxy.server;

import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;

/**
 * 任务管理器
 * <p>
 * 维护待执行任务队列（扩展轮询拉取）+ 任务索引（chunk/done/error 回传时查询）。
 * </p>
 */
public class TaskManager {

    private static final Logger log = LoggerFactory.getLogger(TaskManager.class);

    /** 待执行任务队列（有界，防OOM） */
    private final BlockingQueue<Task> pendingQueue;
    /** 任务索引：taskId → Task */
    private final ConcurrentMap<String, Task> taskMap = new ConcurrentHashMap<>();
    /** 错误任务保留时长（30s） */
    private static final long ERROR_RETENTION_MILLIS = 30_000L;
    /** 扩展在线判定：最近 5 分钟内有 poll 即视为在线 */
    private static final long EXTENSION_ONLINE_WINDOW_MS = 5 * 60 * 1000L;

    private volatile long lastPollTime = 0L;

    /** 扩展最近上报的健康状态（null 表示扩展从未上报） */
    private volatile java.util.Map<String, Object> extensionHealthReport = null;
    /** 扩展健康上报时间戳 */
    private volatile long extensionHealthReportTime = 0L;
    /** 健康上报有效期：5 分钟 */
    private static final long HEALTH_REPORT_TTL_MS = 5 * 60 * 1000L;

    public TaskManager() {
        this(100);
    }

    public TaskManager(int queueCapacity) {
        this.pendingQueue = new ArrayBlockingQueue<>(queueCapacity);
    }

    /** 扩展上报健康状态 */
    public void reportExtensionHealth(java.util.Map<String, Object> report) {
        this.extensionHealthReport = report == null ? null : new java.util.concurrent.ConcurrentHashMap<>(report);
        this.extensionHealthReportTime = System.currentTimeMillis();
        log.debug("扩展上报健康状态: {}", report);
    }

    /** 获取扩展最近上报的健康状态（过期返回 null） */
    public java.util.Map<String, Object> getExtensionHealthReport() {
        if (extensionHealthReport == null) return null;
        if (System.currentTimeMillis() - extensionHealthReportTime > HEALTH_REPORT_TTL_MS) {
            return null;  // 上报过期
        }
        return extensionHealthReport;
    }

    /** 获取扩展最近上报时间戳（仅用于计算 age，调用方不直接使用） */
    public long getExtensionHealthReportTime() {
        return extensionHealthReportTime;
    }

    /** 提交任务入队 */
    public void submit(Task task) throws LlmProxyException {
        if (task == null || task.getTaskId() == null) {
            throw new LlmProxyException(ErrorCode.INVALID_REQUEST, "task 或 taskId 不能为空");
        }
        if (taskMap.containsKey(task.getTaskId())) {
            throw new LlmProxyException(ErrorCode.TASK_ALREADY_EXISTS, "任务已存在：" + task.getTaskId());
        }
        boolean ok = pendingQueue.offer(task);
        if (!ok) {
            throw new LlmProxyException(ErrorCode.TASK_QUEUE_FULL,
                    "任务队列已满（容量 " + pendingQueue.size() + "），请稍后重试");
        }
        taskMap.put(task.getTaskId(), task);
        log.info("任务已入队：taskId={}, provider={}, userId={}",
                task.getTaskId(), task.getProviderId(), task.getUserId());
    }

    /** 扩展轮询拉取任务（阻塞 5s 等待） */
    public Optional<Task> poll(long timeoutMs) throws InterruptedException {
        lastPollTime = System.currentTimeMillis();
        Task task = pendingQueue.poll(timeoutMs, TimeUnit.MILLISECONDS);
        if (task != null) {
            task.markRunning();
            log.info("任务被扩展拉取：taskId={}", task.getTaskId());
        }
        return Optional.ofNullable(task);
    }

    /** 查询任务（chunk/done/error 用） */
    public Optional<Task> find(String taskId) {
        if (taskId == null) return Optional.empty();
        return Optional.ofNullable(taskMap.get(taskId));
    }

    /** 标记错误并延迟清理 */
    public void markError(String taskId, ErrorCode code, String message) {
        find(taskId).ifPresent(t -> {
            t.pushError(code, message);
            log.warn("任务标记错误：taskId={}, code={}, msg={}", taskId, code, message);
            scheduleCleanup(taskId, ERROR_RETENTION_MILLIS);
        });
    }

    /** 任务完成后从索引中移除（保留一段时间供查询） */
    public void markCompleted(String taskId) {
        scheduleCleanup(taskId, ERROR_RETENTION_MILLIS);
    }

    /** 取消任务 */
    public boolean cancel(String taskId) {
        Optional<Task> opt = find(taskId);
        if (opt.isEmpty()) return false;
        Task task = opt.get();
        if (task.isDone()) return false;
        task.pushCancelled();
        pendingQueue.remove(task);
        scheduleCleanup(taskId, 0);
        return true;
    }

    /** 扩展是否在线（最近 5 分钟内有 poll） */
    public boolean isExtensionOnline() {
        return System.currentTimeMillis() - lastPollTime < EXTENSION_ONLINE_WINDOW_MS;
    }

    /** 当前活跃任务数（队列 + 索引中未完成的） */
    public int getActiveCount() {
        int count = pendingQueue.size();
        for (Task t : taskMap.values()) {
            if (!t.isDone()) count++;
        }
        return count;
    }

    /** 列出所有任务（管理/调试用） */
    public List<Task> listAll() {
        return new ArrayList<>(taskMap.values());
    }

    private void scheduleCleanup(String taskId, long delayMs) {
        Thread t = new Thread(() -> {
            try {
                Thread.sleep(delayMs);
                taskMap.remove(taskId);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "TaskManager-Cleanup-" + taskId);
        t.setDaemon(true);
        t.start();
    }
}
