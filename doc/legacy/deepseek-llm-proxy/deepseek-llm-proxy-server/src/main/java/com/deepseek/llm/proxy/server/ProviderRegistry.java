package com.deepseek.llm.proxy.server;

import com.deepseek.llm.proxy.core.BrowserExtensionProvider;
import com.deepseek.llm.proxy.core.LlmProvider;
import com.deepseek.llm.proxy.core.ProviderHealth;
import com.deepseek.llm.proxy.core.ProviderHealthChecker;
import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import com.deepseek.llm.proxy.core.model.ProviderInfo;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

/**
 * Provider 注册中心
 * <p>
 * 启动时收集所有 {@code LlmProvider} Bean，建立 id → Provider 索引。
 * 支持 Spring Bean 自动注册 + 编程式手动注册。
 * </p>
 * <p>
 * 同时维护 {@link ProviderHealthChecker} 索引，支持运行时健康检查。
 * </p>
 */
public class ProviderRegistry {

    private static final Logger log = LoggerFactory.getLogger(ProviderRegistry.class);

    private final ConcurrentMap<String, LlmProvider> providers = new ConcurrentHashMap<>();
    /** 健康检查器索引：providerId → checker */
    private final ConcurrentMap<String, ProviderHealthChecker> healthCheckers = new ConcurrentHashMap<>();

    public ProviderRegistry() {
    }

    public ProviderRegistry(List<LlmProvider> providerBeans) {
        if (providerBeans != null) {
            for (LlmProvider p : providerBeans) {
                register(p);
            }
        }
    }

    /** 注册 Provider */
    public void register(LlmProvider provider) {
        if (provider == null || provider.getId() == null) {
            throw new IllegalArgumentException("provider 或 provider.id 不能为空");
        }
        LlmProvider old = providers.putIfAbsent(provider.getId(), provider);
        if (old != null) {
            log.warn("Provider 已存在，跳过注册：id={}, class={}", provider.getId(),
                    provider.getClass().getName());
            return;
        }
        log.info("注册 Provider：id={}, name={}, class={}", provider.getId(),
                provider.getDisplayName(), provider.getClass().getSimpleName());
    }

    /** 取消注册 */
    public void unregister(String providerId) {
        providers.remove(providerId);
    }

    /** 查找 Provider */
    public Optional<LlmProvider> find(String providerId) {
        if (providerId == null) return Optional.empty();
        return Optional.ofNullable(providers.get(providerId));
    }

    /** 必须找到，否则抛异常 */
    public LlmProvider require(String providerId) throws LlmProxyException {
        return find(providerId).orElseThrow(() ->
                new LlmProxyException(ErrorCode.PROVIDER_NOT_REGISTERED,
                        "Provider 未注册：" + providerId));
    }

    /** 列出所有 Provider 信息 */
    public List<ProviderInfo> listAll() {
        List<ProviderInfo> list = new ArrayList<>(providers.size());
        providers.forEach((id, p) -> {
            ProviderInfo info = new ProviderInfo();
            info.setId(p.getId());
            info.setDisplayName(p.getDisplayName());
            info.setCapabilities(p.getCapabilities());
            info.setSupportedModes(p.getSupportedModes());
            info.setOnline(true);
            list.add(info);
        });
        return list;
    }

    /** 获取所有 BrowserExtensionProvider（与扩展通道配合） */
    public List<BrowserExtensionProvider> listBrowserExtensions() {
        List<BrowserExtensionProvider> list = new ArrayList<>();
        for (LlmProvider p : providers.values()) {
            if (p instanceof BrowserExtensionProvider) {
                list.add((BrowserExtensionProvider) p);
            }
        }
        return list;
    }

    /** 当前注册的 Provider 数量 */
    public int size() {
        return providers.size();
    }

    /** 所有已注册的 Provider ID 集合 */
    public Set<String> listIds() {
        return providers.keySet();
    }

    // ========== 健康检查 ==========

    /** 注册健康检查器 */
    public void registerHealthChecker(ProviderHealthChecker checker) {
        if (checker == null || checker.getProviderId() == null) return;
        healthCheckers.put(checker.getProviderId(), checker);
        log.info("注册健康检查器: providerId={}, class={}",
                checker.getProviderId(), checker.getClass().getSimpleName());
    }

    /** 注销健康检查器 */
    public void unregisterHealthChecker(String providerId) {
        healthCheckers.remove(providerId);
    }

    /**
     * 执行健康检查
     * <p>
     * 若该 Provider 没有注册健康检查器，返回 UNKNOWN 状态。
     * </p>
     */
    public ProviderHealth checkHealth(String providerId) {
        ProviderHealthChecker checker = healthCheckers.get(providerId);
        if (checker == null) {
            ProviderHealth unknown = new ProviderHealth();
            unknown.setProviderId(providerId);
            unknown.setStatus(ProviderHealth.Status.UNKNOWN);
            unknown.setMessage("未注册健康检查器");
            return unknown;
        }
        try {
            return checker.check();
        } catch (Exception e) {
            log.warn("健康检查异常: providerId={}, err={}", providerId, e.getMessage());
            ProviderHealth down = ProviderHealth.down(providerId, "健康检查异常: " + e.getMessage());
            return down;
        }
    }

    /** 检查所有 Provider 健康 */
    public List<ProviderHealth> checkAllHealth() {
        List<ProviderHealth> list = new ArrayList<>();
        for (String id : providers.keySet()) {
            list.add(checkHealth(id));
        }
        return list;
    }
}
