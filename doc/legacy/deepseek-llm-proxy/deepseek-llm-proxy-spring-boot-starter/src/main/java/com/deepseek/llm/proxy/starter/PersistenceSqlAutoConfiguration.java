package com.deepseek.llm.proxy.starter;

import com.deepseek.llm.proxy.persistence.PersistenceConfig;
import com.deepseek.llm.proxy.persistence.PersistenceStrategy;
import com.deepseek.llm.proxy.persistence.sql.SqlPersistenceStrategy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

import javax.sql.DataSource;

/**
 * SQL 持久化自动装配
 * <p>当 persistence.type=sql 时生效。需要业务系统已配置 DataSource 和 JdbcTemplate。</p>
 * <p>
 * 启动时会执行表冲突检测，根据 conflict-resolution 策略处理：
 * <ul>
 *   <li>prompt：抛出 TableConflictException 携带解决方案</li>
 *   <li>rename：改用 tablePrefix 前缀新表</li>
 *   <li>use-existing：直接复用已有表</li>
 *   <li>fail：启动失败</li>
 * </ul>
 * </p>
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass({SqlPersistenceStrategy.class, JdbcTemplate.class})
@ConditionalOnProperty(prefix = "deepseek.llm-proxy.persistence", name = "type", havingValue = "sql")
public class PersistenceSqlAutoConfiguration {

    private static final Logger log = LoggerFactory.getLogger(PersistenceSqlAutoConfiguration.class);

    @Bean
    @ConditionalOnMissingBean(JdbcTemplate.class)
    public JdbcTemplate llmProxyJdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    @ConditionalOnMissingBean(PersistenceStrategy.class)
    public PersistenceStrategy sqlPersistenceStrategy(
            JdbcTemplate jdbcTemplate,
            PersistenceConfig config) {
        log.info("装配 SqlPersistenceStrategy (dialect={}, table-prefix={}, schema-init={}, conflict-resolution={})",
                config.getSql().getDialect(),
                config.getSql().getTablePrefix(),
                config.getSql().getSchemaInit(),
                config.getSql().getConflictResolution());
        return new SqlPersistenceStrategy(jdbcTemplate, config.getSql());
    }
}
