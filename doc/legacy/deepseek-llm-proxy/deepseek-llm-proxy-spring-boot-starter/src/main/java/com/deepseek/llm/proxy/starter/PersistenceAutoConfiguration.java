package com.deepseek.llm.proxy.starter;

import com.deepseek.llm.proxy.core.enums.PersistenceType;
import com.deepseek.llm.proxy.core.exception.PersistenceException;
import com.deepseek.llm.proxy.persistence.NoopPersistenceStrategy;
import com.deepseek.llm.proxy.persistence.PersistenceConfig;
import com.deepseek.llm.proxy.persistence.PersistenceManager;
import com.deepseek.llm.proxy.persistence.PersistenceStrategy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 持久化自动装配
 * <p>
 * 根据 deepseek.llm-proxy.persistence.type 装配对应的 PersistenceStrategy：
 * <ul>
 *   <li>none：NoopPersistenceStrategy（默认）</li>
 *   <li>browser：BrowserPersistenceStrategy（需扩展配合）</li>
 *   <li>sql：SqlPersistenceStrategy（需 JdbcTemplate）</li>
 * </ul>
 * </p>
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(prefix = "deepseek.llm-proxy", name = "enabled", havingValue = "true", matchIfMissing = true)
@EnableConfigurationProperties(LlmProxyProperties.class)
public class PersistenceAutoConfiguration {

    private static final Logger log = LoggerFactory.getLogger(PersistenceAutoConfiguration.class);

    /**
     * 构建 PersistenceConfig（从 properties 映射到 persistence-api 的配置对象）
     */
    @Bean
    @ConditionalOnMissingBean
    public PersistenceConfig persistenceConfig(LlmProxyProperties properties) {
        PersistenceConfig config = new PersistenceConfig();
        LlmProxyProperties.Persistence p = properties.getPersistence();
        config.setType(p.getType());

        // Browser 配置
        PersistenceConfig.BrowserConfig bc = new PersistenceConfig.BrowserConfig();
        bc.setStorageKeyPrefix(p.getBrowser().getStorageKeyPrefix());
        bc.setMaxSizeMb(p.getBrowser().getMaxSizeMb());
        config.setBrowser(bc);

        // SQL 配置
        PersistenceConfig.SqlConfig sc = new PersistenceConfig.SqlConfig();
        sc.setDialect(p.getSql().getDialect());
        sc.setTablePrefix(p.getSql().getTablePrefix());
        sc.setSchemaInit(p.getSql().getSchemaInit());
        sc.setConflictResolution(p.getSql().getConflictResolution());
        sc.setCustomConversationTable(p.getSql().getCustomConversationTable());
        sc.setCustomMemoryTable(p.getSql().getCustomMemoryTable());
        sc.setFieldMapping(convertFieldMapping(p.getSql().getFieldMapping()));
        config.setSql(sc);

        return config;
    }

    /** 字段映射类型转换 */
    private java.util.Map<String, java.util.Map<String, PersistenceConfig.FieldMapping>> convertFieldMapping(
            java.util.Map<String, java.util.Map<String, LlmProxyProperties.FieldMapping>> src) {
        if (src == null) return null;
        java.util.Map<String, java.util.Map<String, PersistenceConfig.FieldMapping>> dst = new java.util.HashMap<>();
        src.forEach((k, v) -> {
            java.util.Map<String, PersistenceConfig.FieldMapping> inner = new java.util.HashMap<>();
            v.forEach((fk, fv) -> {
                PersistenceConfig.FieldMapping fm = new PersistenceConfig.FieldMapping();
                fm.setColumn(fv.getColumn());
                fm.setMissingPolicy(fv.getMissingPolicy());
                fm.setDefaultValue(fv.getDefaultValue());
                inner.put(fk, fm);
            });
            dst.put(k, inner);
        });
        return dst;
    }

    /**
     * 默认 Noop 策略
     */
    @Bean
    @ConditionalOnMissingBean(PersistenceStrategy.class)
    public PersistenceStrategy defaultPersistenceStrategy(LlmProxyProperties properties) {
        if (properties.getPersistence().getType() == PersistenceType.NONE) {
            log.info("DeepSeek LLM Proxy 持久化未启用 (type=none)，使用 NoopPersistenceStrategy");
            return new NoopPersistenceStrategy();
        }
        // 由具体的 PersistenceBrowserAutoConfiguration / PersistenceSqlAutoConfiguration 装配
        return new NoopPersistenceStrategy();
    }

    /**
     * PersistenceManager 装配
     */
    @Bean
    @ConditionalOnMissingBean
    public PersistenceManager persistenceManager(
            PersistenceConfig config,
            ObjectProvider<PersistenceStrategy> strategyProvider) {

        final PersistenceStrategy strategy = strategyProvider.getIfAvailable(NoopPersistenceStrategy::new);

        return new PersistenceManager() {
            private volatile boolean initialized = false;

            @Override
            public PersistenceStrategy getStrategy() {
                return strategy;
            }

            @Override
            public PersistenceType getType() {
                return config.getType();
            }

            @Override
            public void initialize() throws PersistenceException {
                if (initialized) {
                    return;
                }
                log.info("初始化 DeepSeek LLM Proxy 持久化：type={}", config.getType());
                strategy.initialize();
                initialized = true;
                log.info("DeepSeek LLM Proxy 持久化初始化完成");
            }

            @Override
            public boolean isHealthy() {
                return strategy.isHealthy();
            }

            @Override
            public void destroy() throws PersistenceException {
                if (initialized) {
                    strategy.destroy();
                    initialized = false;
                }
            }
        };
    }
}
