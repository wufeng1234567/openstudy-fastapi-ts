package com.deepseek.llm.proxy.server;

import com.deepseek.llm.proxy.core.LlmProvider;
import com.deepseek.llm.proxy.core.ProviderHealthChecker;
import com.deepseek.llm.proxy.core.prompt.PromptManager;
import com.deepseek.llm.proxy.persistence.ConversationRepository;
import com.deepseek.llm.proxy.server.prompt.ClasspathPromptLoader;
import com.deepseek.llm.proxy.server.prompt.DefaultPromptRegistry;
import com.deepseek.llm.proxy.server.prompt.PromptController;
import com.deepseek.llm.proxy.server.prompt.PromptProperties;
import com.deepseek.llm.proxy.server.prompt.PromptTemplateEngine;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter;

import java.util.List;

/**
 * Server 模块自动装配
 * <p>
 * 仅在 Servlet Web 环境下生效，自动注册：
 * <ul>
 *   <li>TaskManager：任务队列</li>
 *   <li>ProviderRegistry：Provider 注册中心（自动收集所有 LlmProvider Bean）</li>
 *   <li>PromptManager：提示词管理器（含 classpath 扫描）</li>
 *   <li>ChatService / OcrService：业务服务（注入 PromptManager）</li>
 *   <li>LlmProxyController / ExtensionPollController / PromptController：REST 端点</li>
 * </ul>
 * </p>
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
@ConditionalOnClass({RequestMappingHandlerAdapter.class, TaskManager.class})
@ConditionalOnProperty(prefix = "deepseek.llm-proxy", name = "enabled", havingValue = "true", matchIfMissing = true)
@EnableConfigurationProperties(PromptProperties.class)
public class LlmProxyServerAutoConfiguration {

    private static final Logger log = LoggerFactory.getLogger(LlmProxyServerAutoConfiguration.class);

    public LlmProxyServerAutoConfiguration() {
        log.info("DeepSeek LLM Proxy Server AutoConfiguration loaded");
    }

    @Bean
    @ConditionalOnMissingBean
    public TaskManager taskManager(
            @Value("${deepseek.llm-proxy.task-queue.capacity:100}") int queueCapacity) {
        log.info("装配 TaskManager（queueCapacity={}）", queueCapacity);
        return new TaskManager(queueCapacity);
    }

    @Bean
    @ConditionalOnMissingBean
    public ProviderRegistry providerRegistry(ObjectProvider<LlmProvider> providerProvider,
                                             ObjectProvider<ProviderHealthChecker> healthCheckerProvider) {
        List<LlmProvider> providers = providerProvider.orderedStream().toList();
        ProviderRegistry registry = new ProviderRegistry(providers);
        // 自动收集所有 ProviderHealthChecker Bean
        List<ProviderHealthChecker> checkers = healthCheckerProvider.orderedStream().toList();
        for (ProviderHealthChecker checker : checkers) {
            registry.registerHealthChecker(checker);
        }
        log.info("装配 ProviderRegistry（{} 个 Provider，{} 个健康检查器）",
                providers.size(), checkers.size());
        return registry;
    }

    /** DeepSeek 默认健康检查器（依赖 TaskManager，自动装配） */
    @Bean
    @ConditionalOnMissingBean(name = "deepSeekHealthChecker")
    @ConditionalOnProperty(prefix = "deepseek.llm-proxy", name = "enabled", havingValue = "true", matchIfMissing = true)
    public ProviderHealthChecker deepSeekHealthChecker(TaskManager taskManager) {
        log.info("装配 DeepSeekHealthChecker");
        return new DeepSeekHealthChecker(taskManager);
    }

    // ========== 提示词管理 ==========

    @Bean
    @ConditionalOnMissingBean
    public PromptTemplateEngine promptTemplateEngine() {
        return new PromptTemplateEngine();
    }

    @Bean
    @ConditionalOnMissingBean
    public ClasspathPromptLoader classpathPromptLoader(PromptProperties props,
                                                       PromptTemplateEngine engine) {
        return new ClasspathPromptLoader(props.getClasspathLocation(), engine);
    }

    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnProperty(prefix = "deepseek.llm-proxy.prompt", name = "enabled", havingValue = "true", matchIfMissing = true)
    public DefaultPromptRegistry promptRegistry(ClasspathPromptLoader loader) {
        log.info("装配 DefaultPromptRegistry（classpath: {}）", loader.getClasspathLocation());
        return new DefaultPromptRegistry(loader);
    }

    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnProperty(prefix = "deepseek.llm-proxy.prompt", name = "enabled", havingValue = "true", matchIfMissing = true)
    public PromptManager promptManager(DefaultPromptRegistry registry) {
        log.info("装配 PromptManager（已加载 {} 个模板）", registry.list().size());
        return new PromptManager(registry);
    }

    // ========== 持久化（会话管理） ==========

    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnBean(ConversationRepository.class)
    public ConversationService conversationService(ConversationRepository repository) {
        log.info("装配 ConversationService（repository={}）", repository.getClass().getSimpleName());
        return new ConversationService(repository);
    }

    // ========== 业务服务 ==========

    @Bean
    @ConditionalOnMissingBean
    public ChatService chatService(TaskManager taskManager,
                                   ProviderRegistry providerRegistry,
                                   @Value("${deepseek.llm-proxy.timeout-ms:300000}") long defaultTimeoutMs,
                                   ObjectProvider<PromptManager> promptManagerProvider,
                                   PromptProperties promptProperties,
                                   ObjectProvider<ConversationService> conversationServiceProvider) {
        PromptManager pm = promptManagerProvider.getIfAvailable();
        String defaultChatPromptId = pm != null ? promptProperties.getDefaultChatPromptId() : null;
        ConversationService cs = conversationServiceProvider.getIfAvailable();
        log.info("装配 ChatService（defaultTimeoutMs={}, promptManager={}, defaultChatPromptId={}, conversationService={}）",
                defaultTimeoutMs, pm != null, defaultChatPromptId, cs != null);
        return new ChatService(taskManager, providerRegistry, defaultTimeoutMs, pm, defaultChatPromptId, cs);
    }

    @Bean
    @ConditionalOnMissingBean
    public OcrService ocrService(ChatService chatService,
                                 ProviderRegistry providerRegistry,
                                 @Value("${deepseek.llm-proxy.timeout-ms:300000}") long defaultTimeoutMs,
                                 ObjectProvider<PromptManager> promptManagerProvider,
                                 PromptProperties promptProperties) {
        PromptManager pm = promptManagerProvider.getIfAvailable();
        log.info("装配 OcrService（promptManager={}, defaultOcrPromptId={}, defaultOcrStructuredPromptId={}）",
                pm != null, promptProperties.getDefaultOcrPromptId(), promptProperties.getDefaultOcrStructuredPromptId());
        return new OcrService(chatService, providerRegistry, defaultTimeoutMs, pm,
                promptProperties.getDefaultOcrPromptId(),
                promptProperties.getDefaultOcrStructuredPromptId());
    }

    // ========== REST 端点 ==========

    @Bean
    @ConditionalOnMissingBean
    public LlmProxyController llmProxyController(ChatService chatService,
                                                 OcrService ocrService,
                                                 TaskManager taskManager,
                                                 ProviderRegistry providerRegistry) {
        return new LlmProxyController(chatService, ocrService, taskManager, providerRegistry);
    }

    @Bean
    @ConditionalOnMissingBean
    public ExtensionPollController extensionPollController(TaskManager taskManager,
                                                           ChatService chatService,
                                                           ProviderRegistry providerRegistry,
                                                           org.springframework.core.env.Environment env) {
        return new ExtensionPollController(taskManager, chatService, providerRegistry, env);
    }

    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnProperty(prefix = "deepseek.llm-proxy.prompt", name = "enabled", havingValue = "true", matchIfMissing = true)
    public PromptController promptController(PromptManager promptManager) {
        log.info("装配 PromptController");
        return new PromptController(promptManager);
    }

    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnBean(ConversationService.class)
    public ConversationController conversationController(ConversationService conversationService) {
        log.info("装配 ConversationController");
        return new ConversationController(conversationService);
    }
}
