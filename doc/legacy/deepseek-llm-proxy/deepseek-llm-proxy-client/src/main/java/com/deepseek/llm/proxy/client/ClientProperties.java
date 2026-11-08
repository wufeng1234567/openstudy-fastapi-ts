package com.deepseek.llm.proxy.client;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 客户端配置属性
 * <p>前缀：deepseek.llm-proxy.client</p>
 */
@ConfigurationProperties(prefix = "deepseek.llm-proxy.client")
public class ClientProperties {

    /** 客户端类型：http / ws / mock */
    private String type = "http";

    /** 服务端基础 URL（HTTP 模式） */
    private String baseUrl = "http://127.0.0.1:8086";

    /** WebSocket URL（WS 模式） */
    private String wsUrl = "ws://127.0.0.1:8086/ws/llm-proxy";

    /** 认证 token */
    private String token;

    /** 连接超时（毫秒） */
    private int connectTimeoutMs = 10000;

    /** 读超时（毫秒） */
    private int readTimeoutMs = 600000;

    public String getType() { return type; }
    public void setType(String type) { this.type = type; }
    public String getBaseUrl() { return baseUrl; }
    public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }
    public String getWsUrl() { return wsUrl; }
    public void setWsUrl(String wsUrl) { this.wsUrl = wsUrl; }
    public String getToken() { return token; }
    public void setToken(String token) { this.token = token; }
    public int getConnectTimeoutMs() { return connectTimeoutMs; }
    public void setConnectTimeoutMs(int connectTimeoutMs) { this.connectTimeoutMs = connectTimeoutMs; }
    public int getReadTimeoutMs() { return readTimeoutMs; }
    public void setReadTimeoutMs(int readTimeoutMs) { this.readTimeoutMs = readTimeoutMs; }
}
