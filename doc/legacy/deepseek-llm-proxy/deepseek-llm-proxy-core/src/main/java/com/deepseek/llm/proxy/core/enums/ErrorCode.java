package com.deepseek.llm.proxy.core.enums;

/**
 * 错误码枚举
 * <p>
 * 规则：5 位整数，分段：
 * <ul>
 *   <li>1xxxx - 通用错误</li>
 *   <li>2xxxx - Provider / 浏览器扩展</li>
 *   <li>3xxxx - 任务 / 会话</li>
 *   <li>4xxxx - 持久化</li>
 * </ul>
 * </p>
 * <p>每个错误码都有明确的排查建议，详见 docs/error-codes.md。</p>
 */
public enum ErrorCode {

    // ===== 通用 1xxxx =====
    INVALID_REQUEST           (10001, "INVALID_REQUEST",            "请求参数错误"),
    AUTH_FAILED               (10002, "AUTH_FAILED",                "认证失败"),
    RATE_LIMITED              (10003, "RATE_LIMITED",               "请求限流"),
    INTERNAL_ERROR            (10004, "INTERNAL_ERROR",             "内部错误"),
    UNSUPPORTED_FEATURE       (10005, "UNSUPPORTED_FEATURE",        "能力不支持"),
    API_VERSION_NOT_SUPPORTED (10006, "API_VERSION_NOT_SUPPORTED",  "API 版本不支持"),
    NETWORK_ERROR             (10007, "NETWORK_ERROR",              "网络错误"),
    SERIALIZATION_ERROR       (10008, "SERIALIZATION_ERROR",        "序列化错误"),

    // ===== Provider / 扩展 2xxxx =====
    PROVIDER_OFFLINE          (20001, "PROVIDER_OFFLINE",           "扩展未连接或 Provider 离线"),
    PROVIDER_NOT_REGISTERED   (20002, "PROVIDER_NOT_REGISTERED",    "Provider 未注册"),
    PROVIDER_ERROR            (20003, "PROVIDER_ERROR",             "上游 Provider 错误"),
    DOM_SELECTOR_INVALID      (20004, "DOM_SELECTOR_INVALID",       "网页 DOM 选择器失效"),
    LOGIN_REQUIRED            (20005, "LOGIN_REQUIRED",             "目标网页未登录"),
    INTERCEPT_FAILED          (20006, "INTERCEPT_FAILED",           "流式输出拦截失败"),
    INJECT_FAILED             (20007, "INJECT_FAILED",              "网页注入失败"),
    EXTENSION_TIMEOUT         (20008, "EXTENSION_TIMEOUT",          "扩展响应超时"),

    // ===== 任务 / 会话 3xxxx =====
    TASK_TIMEOUT              (30001, "TASK_TIMEOUT",               "任务超时"),
    TASK_CANCELLED            (30002, "TASK_CANCELLED",             "任务已取消"),
    TASK_NOT_FOUND            (30003, "TASK_NOT_FOUND",             "任务不存在"),
    TASK_QUEUE_FULL           (30004, "TASK_QUEUE_FULL",            "任务队列已满"),
    SESSION_NOT_FOUND         (30005, "SESSION_NOT_FOUND",          "会话不存在"),
    MAX_LOOPS_EXCEEDED        (30006, "MAX_LOOPS_EXCEEDED",         "工具循环超过最大次数"),
    TASK_ALREADY_EXISTS       (30007, "TASK_ALREADY_EXISTS",        "任务已存在"),
    DUPLICATE_SUBMIT          (30008, "DUPLICATE_SUBMIT",           "数据正在处理，请勿重复提交"),

    // ===== 持久化 4xxxx =====
    PERSISTENCE_NOT_CONFIGURED (40001, "PERSISTENCE_NOT_CONFIGURED", "未配置持久化策略"),
    PERSISTENCE_INIT_FAILED    (40002, "PERSISTENCE_INIT_FAILED",    "持久化初始化失败"),
    TABLE_NOT_FOUND            (40003, "TABLE_NOT_FOUND",            "表不存在"),
    TABLE_SCHEMA_MISMATCH      (40004, "TABLE_SCHEMA_MISMATCH",      "表结构不匹配"),
    TABLE_CONFLICT             (40005, "TABLE_CONFLICT",             "表已存在且功能冲突"),
    PERSISTENCE_WRITE_FAILED   (40006, "PERSISTENCE_WRITE_FAILED",   "持久化写入失败"),
    PERSISTENCE_READ_FAILED    (40007, "PERSISTENCE_READ_FAILED",    "持久化读取失败"),
    PERSISTENCE_DESTROY_FAILED (40008, "PERSISTENCE_DESTROY_FAILED", "持久化销毁失败"),
    DIALECT_NOT_SUPPORTED      (40009, "DIALECT_NOT_SUPPORTED",      "数据库方言不支持"),
    BROWSER_STORAGE_QUOTA      (40010, "BROWSER_STORAGE_QUOTA",      "浏览器存储配额不足"),
    BROWSER_STORAGE_UNAVAILABLE(40011, "BROWSER_STORAGE_UNAVAILABLE","浏览器存储不可用"),
    FIELD_MAPPING_INVALID      (40012, "FIELD_MAPPING_INVALID",      "字段映射配置无效"),
    CONVERSATION_NOT_FOUND     (40013, "CONVERSATION_NOT_FOUND",     "会话记录不存在"),
    MEMORY_NOT_FOUND           (40014, "MEMORY_NOT_FOUND",           "记忆记录不存在");

    private final int code;
    private final String name;
    private final String message;

    ErrorCode(int code, String name, String message) {
        this.code = code;
        this.name = name;
        this.message = message;
    }

    public int getCode() {
        return code;
    }

    public String getName() {
        return name;
    }

    public String getMessage() {
        return message;
    }
}
