package com.deepseek.llm.proxy.ext.deepseek;

import com.deepseek.llm.proxy.core.enums.Capability;
import com.deepseek.llm.proxy.core.enums.ProviderMode;

import java.util.EnumSet;
import java.util.List;
import java.util.Set;

/**
 * DeepSeek 网页版 Provider 常量定义
 * <p>集中管理 ID、能力集、模式、host pattern、登录 URL 等常量。</p>
 */
public final class DeepSeekProviderConstants {

    private DeepSeekProviderConstants() {}

    /** Provider ID */
    public static final String ID = "deepseek-free";
    /** 展示名称 */
    public static final String DISPLAY_NAME = "DeepSeek Free (网页代理)";
    /** 网页 host pattern */
    public static final String HOST_PATTERN = "https://chat.deepseek.com/*";
    /** 登录 URL */
    public static final String LOGIN_URL = "https://chat.deepseek.com/";
    /** 拦截器脚本路径（在扩展包内的相对路径） */
    public static final String INTERCEPTOR_SCRIPT_PATH = "providers/deepseek/interceptor.js";

    /** 能力集 */
    public static final Set<Capability> CAPABILITIES = EnumSet.of(
            Capability.STREAMING,
            Capability.THINKING,
            Capability.IMAGES,
            Capability.FILES,
            Capability.MODES,
            Capability.TOOLS,
            Capability.MEMORY
    );

    /** 支持的对话模式 */
    public static final List<ProviderMode> SUPPORTED_MODES = List.of(
            ProviderMode.DEFAULT,
            ProviderMode.EXPERT,
            ProviderMode.VISION
    );

    // ===== DOM 选择器 =====
    /** 输入框：textarea 或 contenteditable */
    public static final String SEL_INPUT = "textarea, [contenteditable=\"true\"]";
    /** 发送按钮组（多重选择器） */
    public static final String SEL_SEND_BUTTON =
            "button[class*=\"send\"], [role=\"button\"][class*=\"send\"], " +
            "[aria-label*=\"send\"], [aria-label*=\"发送\"], " +
            "button[type=\"submit\"], .send-btn";
    /** 深度思考开关 */
    public static final String SEL_DEEP_THINK_TOGGLE = ".ds-toggle-button";
    /** 对话模式 radio */
    public static final String SEL_MODE_RADIO = "[role=\"radio\"][data-model-type]";
    /** 文件上传 input */
    public static final String SEL_FILE_INPUT = "input[type=\"file\"]";
    /** 登录表单（存在表示未登录） */
    public static final String SEL_LOGIN_FORM =
            "input[type=\"password\"], form[action*=\"login\"], [class*=\"login\"], [class*=\"signin\"]";
    /** 已登录标识 */
    public static final String SEL_AVATAR =
            "[class*=\"avatar\"], [class*=\"user-menu\"], img[alt*=\"avatar\"]";

    // ===== SSE 拦截 =====
    /** SSE 拦截 URL 关键字过滤（任一匹配则拦截） */
    public static final String SSE_URL_KEYWORD = "completion";

    // ===== 任务序列化协议 =====
    public static final String TASK_TYPE_CHAT = "chat";
    public static final String TASK_TYPE_OCR = "ocr";
}
