package com.deepseek.llm.proxy.server;

import com.deepseek.llm.proxy.core.ProviderHealth;
import com.deepseek.llm.proxy.core.ProviderHealthChecker;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;

/**
 * DeepSeek Provider 健康检查器
 * <p>
 * 通过 {@link TaskManager#getExtensionHealthReport()} 获取扩展最近上报的 DS 标签页状态，
 * 给出运行时的真实可用性判断（弥补 Provider 静态能力声明的不足）。
 * </p>
 * <p>
 * 状态判定规则：
 * <ul>
 *   <li>UP：扩展在线 + DS 标签页已打开 + 已登录</li>
 *   <li>DEGRADED：扩展在线但 DS 未打开 / 未登录 / 上报过期</li>
 *   <li>DOWN：扩展离线</li>
 * </ul>
 * </p>
 */
public class DeepSeekHealthChecker implements ProviderHealthChecker {

    private static final Logger log = LoggerFactory.getLogger(DeepSeekHealthChecker.class);
    private static final String PROVIDER_ID = "deepseek-free";

    private final TaskManager taskManager;

    public DeepSeekHealthChecker(TaskManager taskManager) {
        this.taskManager = taskManager;
    }

    @Override
    public String getProviderId() {
        return PROVIDER_ID;
    }

    @Override
    public ProviderHealth check() {
        ProviderHealth health = new ProviderHealth();
        health.setProviderId(PROVIDER_ID);

        // 1. 扩展是否在线
        boolean extensionOnline = taskManager.isExtensionOnline();
        health.setExtensionOnline(extensionOnline);

        if (!extensionOnline) {
            health.setStatus(ProviderHealth.Status.DOWN);
            health.setMessage("扩展离线（最近 5 分钟无 poll）");
            health.setTargetTabOpen(false);
            health.setTargetLoggedIn(false);
            return health;
        }

        // 2. 获取扩展上报的健康状态
        Map<String, Object> report = taskManager.getExtensionHealthReport();
        if (report == null) {
            health.setStatus(ProviderHealth.Status.DEGRADED);
            health.setMessage("扩展在线但未上报健康状态（或上报已过期）");
            health.setTargetTabOpen(false);
            health.setTargetLoggedIn(false);
            return health;
        }

        // 3. 解析上报字段
        Object dsTabOpenObj = report.get("dsTabOpen");
        Object loggedInObj = report.get("loggedIn");
        Object providerIdObj = report.get("providerId");
        boolean dsTabOpen = dsTabOpenObj instanceof Boolean ? (Boolean) dsTabOpenObj
                : dsTabOpenObj instanceof String && "true".equalsIgnoreCase((String) dsTabOpenObj);
        boolean loggedIn = loggedInObj instanceof Boolean ? (Boolean) loggedInObj
                : loggedInObj instanceof String && "true".equalsIgnoreCase((String) loggedInObj);

        health.setTargetTabOpen(dsTabOpen);
        health.setTargetLoggedIn(loggedIn);

        // 4. 任务统计（可选）
        Object pendingObj = report.get("pendingTasks");
        Object runningObj = report.get("runningTasks");
        if (pendingObj instanceof Number) {
            health.setPendingTasks(((Number) pendingObj).intValue());
        }
        if (runningObj instanceof Number) {
            health.setRunningTasks(((Number) runningObj).intValue());
        }

        // 5. 状态判定
        if (dsTabOpen && loggedIn) {
            health.setStatus(ProviderHealth.Status.UP);
            health.setMessage("OK");
        } else if (dsTabOpen && !loggedIn) {
            health.setStatus(ProviderHealth.Status.DEGRADED);
            health.setMessage("DeepSeek 标签页已打开但未登录");
        } else {
            health.setStatus(ProviderHealth.Status.DEGRADED);
            health.setMessage("DeepSeek 标签页未打开");
        }

        log.debug("DeepSeek 健康检查: status={}, tabOpen={}, loggedIn={}",
                health.getStatus(), dsTabOpen, loggedIn);
        return health;
    }
}
