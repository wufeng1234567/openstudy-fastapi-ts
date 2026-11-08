package com.deepseek.llm.proxy.core;

/**
 * Provider 健康检查结果
 * <p>
 * 描述某个 Provider 在当前时刻的可用性状态，由 {@link ProviderHealthChecker} 返回。
 * </p>
 */
public class ProviderHealth {

    /** 健康状态枚举 */
    public enum Status {
        /** 完全可用 */
        UP,
        /** 部分可用（如未登录但页面已打开） */
        DEGRADED,
        /** 不可用 */
        DOWN,
        /** 未知（健康检查器未实现或异常） */
        UNKNOWN
    }

    private Status status;
    /** Provider ID */
    private String providerId;
    /** 扩展是否在线（最近 5 分钟内有 poll） */
    private boolean extensionOnline;
    /** 目标网页是否已打开（如 DS 标签页） */
    private boolean targetTabOpen;
    /** 目标网页是否已登录 */
    private boolean targetLoggedIn;
    /** 待处理任务数 */
    private int pendingTasks;
    /** 运行中任务数 */
    private int runningTasks;
    /** 详细信息（如失败原因） */
    private String message;
    /** 检查时间戳（毫秒） */
    private long checkedAt;

    public ProviderHealth() {
        this.status = Status.UNKNOWN;
        this.checkedAt = System.currentTimeMillis();
    }

    public static ProviderHealth up(String providerId) {
        ProviderHealth h = new ProviderHealth();
        h.providerId = providerId;
        h.status = Status.UP;
        h.message = "OK";
        return h;
    }

    public static ProviderHealth down(String providerId, String reason) {
        ProviderHealth h = new ProviderHealth();
        h.providerId = providerId;
        h.status = Status.DOWN;
        h.message = reason;
        return h;
    }

    public static ProviderHealth degraded(String providerId, String reason) {
        ProviderHealth h = new ProviderHealth();
        h.providerId = providerId;
        h.status = Status.DEGRADED;
        h.message = reason;
        return h;
    }

    public Status getStatus() { return status; }
    public void setStatus(Status status) { this.status = status; }
    public String getProviderId() { return providerId; }
    public void setProviderId(String providerId) { this.providerId = providerId; }
    public boolean isExtensionOnline() { return extensionOnline; }
    public void setExtensionOnline(boolean extensionOnline) { this.extensionOnline = extensionOnline; }
    public boolean isTargetTabOpen() { return targetTabOpen; }
    public void setTargetTabOpen(boolean targetTabOpen) { this.targetTabOpen = targetTabOpen; }
    public boolean isTargetLoggedIn() { return targetLoggedIn; }
    public void setTargetLoggedIn(boolean targetLoggedIn) { this.targetLoggedIn = targetLoggedIn; }
    public int getPendingTasks() { return pendingTasks; }
    public void setPendingTasks(int pendingTasks) { this.pendingTasks = pendingTasks; }
    public int getRunningTasks() { return runningTasks; }
    public void setRunningTasks(int runningTasks) { this.runningTasks = runningTasks; }
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
    public long getCheckedAt() { return checkedAt; }
    public void setCheckedAt(long checkedAt) { this.checkedAt = checkedAt; }
}
