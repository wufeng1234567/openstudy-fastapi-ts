package com.deepseek.llm.proxy.core.prompt;

import java.util.List;

/**
 * 提示词注册中心
 * <p>
 * 启动时加载所有提示词模板，按 ID 索引；支持运行时注册新模板与热加载。
 * </p>
 */
public interface PromptRegistry {

    /**
     * 按 ID 获取模板（在所有 Provider 范围内查找）
     *
     * @param promptId 提示词 ID
     * @return 模板实例，未找到返回 null
     */
    PromptTemplate get(String promptId);

    /**
     * 按 Provider + 场景获取模板
     * <p>
     * 查找顺序：先找 providerId + scene 对应模板，未命中再找 _global + scene。
     * </p>
     *
     * @param providerId Provider ID（null 走 _global）
     * @param scene      场景
     * @return 模板实例，未找到返回 null
     */
    PromptTemplate get(String providerId, String scene);

    /**
     * 列出所有模板
     */
    List<PromptTemplate> list();

    /**
     * 运行时注册新模板
     */
    void register(PromptTemplate template);

    /**
     * 重新加载所有模板（热加载）
     *
     * @throws PromptException 加载失败
     */
    void reload() throws PromptException;
}
