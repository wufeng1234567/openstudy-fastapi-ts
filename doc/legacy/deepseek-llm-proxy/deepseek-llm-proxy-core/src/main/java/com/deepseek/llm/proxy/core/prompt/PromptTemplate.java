package com.deepseek.llm.proxy.core.prompt;

/**
 * 提示词模板
 * <p>
 * 渲染后的提示词文本。{@link PromptRegistry} 返回此接口的实现，业务层调用 {@link #render(PromptContext)}
 * 得到最终字符串。
 * </p>
 */
public interface PromptTemplate {

    /**
     * 获取模板定义
     */
    PromptDefinition getDefinition();

    /**
     * 渲染模板
     *
     * @param context 变量上下文
     * @return 渲染后的提示词文本
     * @throws PromptException 变量缺失或语法错误
     */
    String render(PromptContext context) throws PromptException;
}
