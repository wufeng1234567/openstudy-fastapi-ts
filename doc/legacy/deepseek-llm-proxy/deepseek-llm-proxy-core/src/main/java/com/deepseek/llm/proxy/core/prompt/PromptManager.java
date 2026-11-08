package com.deepseek.llm.proxy.core.prompt;

import java.util.List;
import java.util.Map;

/**
 * 提示词管理器（业务层入口）
 * <p>
 * 封装 {@link PromptRegistry}，提供业务友好的渲染 API。同时承担以下职责：
 * <ul>
 *   <li>变量校验：检查必填变量是否提供</li>
 *   <li>降级策略：promptId 未命中时回退到 systemPrompt</li>
 *   <li>默认模板：未指定 promptId 时按场景匹配默认模板</li>
 * </ul>
 * </p>
 */
public class PromptManager {

    private final PromptRegistry registry;

    public PromptManager(PromptRegistry registry) {
        this.registry = registry;
    }

    /**
     * 按 ID 渲染提示词
     *
     * @param promptId  提示词 ID
     * @param variables 模板变量
     * @return 渲染后的文本
     * @throws PromptException 模板不存在或变量缺失
     */
    public String render(String promptId, Map<String, Object> variables) throws PromptException {
        if (promptId == null || promptId.isEmpty()) {
            throw new PromptException("promptId 不能为空");
        }
        PromptTemplate template = registry.get(promptId);
        if (template == null) {
            throw new PromptException("提示词模板不存在: " + promptId);
        }
        return template.render(PromptContext.of(variables));
    }

    /**
     * 按 Provider + 场景渲染提示词
     */
    public String render(String providerId, String scene, Map<String, Object> variables) throws PromptException {
        PromptTemplate template = registry.get(providerId, scene);
        if (template == null) {
            throw new PromptException("未找到 Provider=" + providerId + " 场景=" + scene + " 的提示词模板");
        }
        return template.render(PromptContext.of(variables));
    }

    /**
     * 渲染（带降级）：promptId 未命中或未提供时，回退到 fallbackText
     *
     * @param promptId     提示词 ID（可为 null）
     * @param variables    模板变量
     * @param fallbackText 降级文本（promptId 为 null 或未命中时使用）
     * @return 渲染后的文本，若 promptId 为 null 则返回 fallbackText
     */
    public String renderOrDefault(String promptId, Map<String, Object> variables, String fallbackText) {
        if (promptId == null || promptId.isEmpty()) {
            return fallbackText;
        }
        try {
            return render(promptId, variables);
        } catch (PromptException e) {
            // 模板不存在或渲染失败，降级到 fallbackText
            return fallbackText;
        }
    }

    /**
     * 查询是否存在指定 ID 的模板
     */
    public boolean exists(String promptId) {
        return registry.get(promptId) != null;
    }

    /**
     * 列出所有模板定义
     */
    public List<PromptTemplate> list() {
        return registry.list();
    }

    /**
     * 触发热加载
     */
    public void reload() throws PromptException {
        registry.reload();
    }

    /**
     * 获取底层 Registry（供 AutoConfiguration 等使用）
     */
    public PromptRegistry getRegistry() {
        return registry;
    }
}
