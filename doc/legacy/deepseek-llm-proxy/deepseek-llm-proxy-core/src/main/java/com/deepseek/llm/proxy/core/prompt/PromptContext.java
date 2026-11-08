package com.deepseek.llm.proxy.core.prompt;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

/**
 * 提示词渲染上下文
 * <p>
 * 携带模板变量集合，传给 {@link PromptTemplate#render(PromptContext)} 进行渲染。
 * </p>
 */
public class PromptContext {

    private final Map<String, Object> variables;

    private PromptContext(Map<String, Object> variables) {
        this.variables = Collections.unmodifiableMap(variables);
    }

    /**
     * 创建空上下文
     */
    public static PromptContext empty() {
        return new PromptContext(new HashMap<>());
    }

    /**
     * 从 Map 创建上下文
     */
    public static PromptContext of(Map<String, Object> variables) {
        return new PromptContext(variables == null ? new HashMap<>() : new HashMap<>(variables));
    }

    /**
     * 链式添加变量
     */
    public PromptContext with(String key, Object value) {
        Map<String, Object> newVars = new HashMap<>(this.variables);
        newVars.put(key, value);
        return new PromptContext(newVars);
    }

    /**
     * 获取变量值（返回 null 表示不存在）
     */
    public Object get(String key) {
        return variables.get(key);
    }

    /**
     * 获取变量值，不存在返回 defaultValue
     */
    public Object getOrDefault(String key, Object defaultValue) {
        return variables.getOrDefault(key, defaultValue);
    }

    /**
     * 获取字符串变量
     */
    public String getString(String key) {
        Object v = variables.get(key);
        return v == null ? null : v.toString();
    }

    /**
     * 获取布尔变量
     */
    public boolean getBoolean(String key, boolean defaultValue) {
        Object v = variables.get(key);
        if (v == null) return defaultValue;
        if (v instanceof Boolean) return (Boolean) v;
        return Boolean.parseBoolean(v.toString());
    }

    /**
     * 判断变量是否存在
     */
    public boolean has(String key) {
        return variables.containsKey(key);
    }

    /**
     * 返回所有变量（只读）
     */
    public Map<String, Object> asMap() {
        return variables;
    }
}
