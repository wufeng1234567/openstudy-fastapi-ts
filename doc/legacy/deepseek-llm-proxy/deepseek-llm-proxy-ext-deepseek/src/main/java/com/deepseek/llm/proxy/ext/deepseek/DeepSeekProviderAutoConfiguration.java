package com.deepseek.llm.proxy.ext.deepseek;

import com.deepseek.llm.proxy.core.LlmProvider;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * DeepSeek Provider 自动装配
 * <p>
 * 默认启用，可通过配置关闭：
 * <pre>
 * deepseek.llm-proxy.providers.deepseek-free.enabled=false
 * </pre>
 * </p>
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(LlmProvider.class)
@ConditionalOnProperty(prefix = "deepseek.llm-proxy.providers.deepseek-free", name = "enabled",
        havingValue = "true", matchIfMissing = true)
public class DeepSeekProviderAutoConfiguration {

    private static final Logger log = LoggerFactory.getLogger(DeepSeekProviderAutoConfiguration.class);

    public DeepSeekProviderAutoConfiguration() {
        log.info("DeepSeek Provider AutoConfiguration loaded");
    }

    @Bean
    @ConditionalOnMissingBean(DeepSeekProvider.class)
    public DeepSeekProvider deepSeekProvider() {
        log.info("装配 DeepSeekProvider");
        return new DeepSeekProvider();
    }
}
