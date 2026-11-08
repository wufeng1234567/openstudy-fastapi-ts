package com.deepseek.llm.proxy.starter;

import com.deepseek.llm.proxy.core.enums.PersistenceType;
import com.deepseek.llm.proxy.persistence.PersistenceConfig;
import com.deepseek.llm.proxy.persistence.PersistenceStrategy;
import com.deepseek.llm.proxy.persistence.browser.BrowserPersistenceStrategy;
import com.deepseek.llm.proxy.persistence.browser.BrowserStorageAdapter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Browser 持久化自动装配
 * <p>当 persistence.type=browser 时生效。</p>
 * <p>
 * 注意：BrowserStorageAdapter 实现需要由业务系统提供（通过 WebSocket 与扩展通信），
 * 本配置仅在 Adapter Bean 存在时生效。
 * </p>
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(BrowserPersistenceStrategy.class)
@ConditionalOnProperty(prefix = "deepseek.llm-proxy.persistence", name = "type", havingValue = "browser")
public class PersistenceBrowserAutoConfiguration {

    private static final Logger log = LoggerFactory.getLogger(PersistenceBrowserAutoConfiguration.class);

    @Bean
    @ConditionalOnMissingBean(PersistenceStrategy.class)
    public PersistenceStrategy browserPersistenceStrategy(
            BrowserStorageAdapter adapter,
            PersistenceConfig config) {
        log.info("装配 BrowserPersistenceStrategy (prefix={}, maxSize={}MB)",
                config.getBrowser().getStorageKeyPrefix(),
                config.getBrowser().getMaxSizeMb());
        return new BrowserPersistenceStrategy(adapter, config.getBrowser());
    }
}
