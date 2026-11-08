package com.deepseek.llm.proxy.core;

import com.deepseek.llm.proxy.core.enums.Phase;
import com.deepseek.llm.proxy.core.model.ChatRequest;
import com.deepseek.llm.proxy.core.model.DomSelectors;
import com.deepseek.llm.proxy.core.model.ParsedStream;
import com.deepseek.llm.proxy.core.model.TaskPayload;

/**
 * 浏览器扩展型 Provider（如 DeepSeek 网页版、Claude 网页版等）
 * <p>
 * 此接口在 LlmProvider 基础上扩展了浏览器扩展相关能力：
 * 拦截器脚本路径、任务序列化、流解析、DOM 选择器配置。
 * </p>
 */
public interface BrowserExtensionProvider extends LlmProvider {

    /**
     * 拦截器脚本路径（在网页 MAIN world 注入）
     * <p>如 "providers/deepseek/interceptor.js"</p>
     */
    String getInterceptorScriptPath();

    /**
     * 把通用 ChatRequest 序列化为扩展任务载荷
     */
    TaskPayload serializeTask(ChatRequest request);

    /**
     * 解析扩展回传的原始 chunk
     *
     * @param rawChunk 扩展回传的原始内容
     * @param phase    当前阶段 THINKING / RESPONSE
     */
    ParsedStream parseChunk(String rawChunk, Phase phase);

    /**
     * 获取该 Provider 网页的 DOM 选择器配置
     */
    DomSelectors getDomSelectors();

    /**
     * 网页 host 匹配模式，如 "https://chat.deepseek.com/*"
     */
    String getHostPattern();

    /**
     * 网站登录 URL（用于登录失效时引导用户）
     */
    default String getLoginUrl() {
        return null;
    }
}
