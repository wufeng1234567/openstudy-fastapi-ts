package com.deepseek.llm.proxy.starter;

import com.deepseek.llm.proxy.core.LlmProxyClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

/**
 * DeepSeek LLM Proxy 主自动装配入口
 * <p>
 * 启用此 Starter 后，业务系统通过 application.yml 配置即可接入 DeepSeek LLM Proxy。
 * </p>
 * <p>
 * 阶段 1：仅装配持久化相关 Bean。客户端 Bean（LlmProxyClient）由阶段 2 提供。
 * </p>
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(LlmProxyClient.class)
@ConditionalOnProperty(prefix = "deepseek.llm-proxy", name = "enabled", havingValue = "true", matchIfMissing = true)
@Import({
        PersistenceAutoConfiguration.class,
        PersistenceBrowserAutoConfiguration.class,
        PersistenceSqlAutoConfiguration.class
})
public class LlmProxyAutoConfiguration {

    private static final Logger log = LoggerFactory.getLogger(LlmProxyAutoConfiguration.class);

    static {
        log.info("DeepSeek LLM Proxy AutoConfiguration loaded");
    }
}
