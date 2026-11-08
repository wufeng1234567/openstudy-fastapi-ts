package com.deepseek.llm.proxy.client;

import com.deepseek.llm.proxy.core.LlmProxyClient;
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
 * 客户端自动装配
 * <p>
 * 根据 deepseek.llm-proxy.client.type 配置选择客户端实现：
 * <ul>
 *   <li>http（默认）：HttpLlmProxyClient</li>
 *   <li>ws：WebSocketLlmProxyClient</li>
 *   <li>mock：MockLlmProxyClient</li>
 * </ul>
 * </p>
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(LlmProxyClient.class)
@ConditionalOnProperty(prefix = "deepseek.llm-proxy", name = "enabled", havingValue = "true", matchIfMissing = true)
@EnableConfigurationProperties(ClientProperties.class)
public class LlmProxyClientAutoConfiguration {

    private static final Logger log = LoggerFactory.getLogger(LlmProxyClientAutoConfiguration.class);

    public LlmProxyClientAutoConfiguration() {
        log.info("DeepSeek LLM Proxy Client AutoConfiguration loaded");
    }

    @Bean
    @ConditionalOnMissingBean
    public LlmProxyClient llmProxyClient(ClientProperties props) {
        String type = props.getType() != null ? props.getType() : "http";
        log.info("装配 LlmProxyClient：type={}, baseUrl={}", type, props.getBaseUrl());

        switch (type.toLowerCase()) {
            case "http":
                return new HttpLlmProxyClient(
                        props.getBaseUrl(),
                        props.getToken(),
                        props.getConnectTimeoutMs(),
                        props.getReadTimeoutMs());
            case "ws":
            case "websocket":
                return new WebSocketLlmProxyClient(props.getWsUrl(), props.getToken());
            case "mock":
                return new MockLlmProxyClient();
            default:
                throw new IllegalArgumentException("未知 client.type：" + type + "。支持：http / ws / mock");
        }
    }
}
