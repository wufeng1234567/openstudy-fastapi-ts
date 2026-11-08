package com.deepseek.llm.proxy.server.prompt;

import com.deepseek.llm.proxy.core.prompt.PromptContext;
import com.deepseek.llm.proxy.core.prompt.PromptException;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 轻量模板引擎
 * <p>
 * 支持以下语法（无第三方依赖，自研实现）：
 * <ul>
 *   <li>{@code ${var}} 变量替换</li>
 *   <li>{@code ${var:默认值}} 带默认值的变量</li>
 *   <li>{@code ${#include "shared/xx.txt"}} 包含子模板（需通过 includeResolver 提供）</li>
 *   <li>{@code ${#if cond}...${/if}} 条件块（cond 为变量名，存在且非空时为真）</li>
 *   <li>{@code ${#if !cond}...${/if}} 条件取反</li>
 *   <li>{@code ${#each list as item}...${/each}} 循环（list 为变量名，指向 List 或数组）</li>
 * </ul>
 * </p>
 * <p>
 * 设计目标：覆盖提示词模板 90% 的常见需求，避免引入 Thymeleaf/Freemarker 等重型框架。
 * </p>
 */
public class PromptTemplateEngine {

    /** 主变量占位符：${var} 或 ${var:default} */
    private static final Pattern VAR_PATTERN = Pattern.compile("\\$\\{([^{}#:][^{}]*)}");

    /** 控制块：${#if ...}/${#each ...}/${/if}/${/each}/${#include "..."} */
    private static final Pattern BLOCK_PATTERN = Pattern.compile(
            "\\$\\{(#if\\s+[^}]+|#each\\s+[^}]+|/#if|/#each|#include\\s+\"[^\"]+\")}");

    /** include 解析器（加载子模板内容） */
    public interface IncludeResolver {
        String resolve(String path) throws PromptException;
    }

    private final IncludeResolver includeResolver;

    public PromptTemplateEngine() {
        this(null);
    }

    public PromptTemplateEngine(IncludeResolver includeResolver) {
        this.includeResolver = includeResolver;
    }

    /**
     * 渲染模板
     *
     * @param template 模板字符串
     * @param context  变量上下文
     * @return 渲染后的文本
     * @throws PromptException 语法错误或变量缺失
     */
    public String render(String template, PromptContext context) throws PromptException {
        if (template == null) return "";
        if (context == null) context = PromptContext.empty();

        // 第一步：先处理 include（递归展开子模板）
        String result = processIncludes(template);

        // 第二步：处理条件块和循环块
        result = processBlocks(result, context);

        // 第三步：替换变量占位符
        result = processVariables(result, context);

        return result;
    }

    /**
     * 处理 include：${#include "path"} → 子模板内容
     */
    private String processIncludes(String template) throws PromptException {
        if (includeResolver == null) return template;
        Matcher m = BLOCK_PATTERN.matcher(template);
        StringBuilder sb = new StringBuilder();
        int last = 0;
        while (m.find()) {
            sb.append(template, last, m.start());
            String token = m.group(1);
            if (token.startsWith("#include")) {
                Matcher im = Pattern.compile("#include\\s+\"([^\"]+)\"").matcher(token);
                if (im.find()) {
                    String path = im.group(1);
                    String content = includeResolver.resolve(path);
                    sb.append(content);
                } else {
                    throw new PromptException("无效的 include 语法: " + m.group(0));
                }
            } else {
                // 其他控制块原样保留，留给后续步骤处理
                sb.append(m.group(0));
            }
            last = m.end();
        }
        sb.append(template, last, template.length());
        return sb.toString();
    }

    /**
     * 处理条件块和循环块
     */
    private String processBlocks(String template, PromptContext context) throws PromptException {
        // 简化实现：先处理 if，再处理 each（不支持嵌套）
        // 实际场景中提示词模板嵌套需求极低，保持实现简单
        String result = template;
        result = processIfBlocks(result, context);
        result = processEachBlocks(result, context);
        return result;
    }

    /**
     * 处理 ${#if var}...${/if} 与 ${#if !var}...${/if}
     */
    private String processIfBlocks(String template, PromptContext context) {
        Pattern ifPattern = Pattern.compile(
                "\\$\\{#if\\s+(!?)([a-zA-Z_][a-zA-Z0-9_]*)\\}(.*?)\\$\\{/if\\}",
                Pattern.DOTALL);
        Matcher m = ifPattern.matcher(template);
        StringBuilder sb = new StringBuilder();
        int last = 0;
        while (m.find()) {
            sb.append(template, last, m.start());
            String negate = m.group(1);
            String varName = m.group(2);
            String body = m.group(3);
            boolean exists = context.has(varName) && isTruthy(context.get(varName));
            if ("!".equals(negate)) exists = !exists;
            if (exists) sb.append(body);
            last = m.end();
        }
        sb.append(template, last, template.length());
        return sb.toString();
    }

    /**
     * 处理 ${#each list as item}...${/each}
     */
    private String processEachBlocks(String template, PromptContext context) {
        Pattern eachPattern = Pattern.compile(
                "\\$\\{#each\\s+([a-zA-Z_][a-zA-Z0-9_]*)\\s+as\\s+([a-zA-Z_][a-zA-Z0-9_]*)\\}(.*?)\\$\\{/each\\}",
                Pattern.DOTALL);
        Matcher m = eachPattern.matcher(template);
        StringBuilder sb = new StringBuilder();
        int last = 0;
        while (m.find()) {
            sb.append(template, last, m.start());
            String listVar = m.group(1);
            String itemVar = m.group(2);
            String body = m.group(3);
            Object listObj = context.get(listVar);
            if (listObj instanceof Iterable) {
                for (Object item : (Iterable<?>) listObj) {
                    PromptContext itemCtx = context.with(itemVar, item);
                    // 在循环体内递归处理变量（不递归处理 if/each，避免复杂化）
                    sb.append(processVariables(body, itemCtx));
                }
            } else if (listObj != null && listObj.getClass().isArray()) {
                for (Object item : (Object[]) listObj) {
                    PromptContext itemCtx = context.with(itemVar, item);
                    sb.append(processVariables(body, itemCtx));
                }
            }
            // listObj 为 null 或非集合类型：跳过整个 each 块
            last = m.end();
        }
        sb.append(template, last, template.length());
        return sb.toString();
    }

    /**
     * 替换 ${var} 和 ${var:default}
     */
    private String processVariables(String template, PromptContext context) {
        Matcher m = VAR_PATTERN.matcher(template);
        StringBuilder sb = new StringBuilder();
        int last = 0;
        while (m.find()) {
            sb.append(template, last, m.start());
            String expr = m.group(1).trim();
            String value = resolveVariable(expr, context);
            sb.append(value);
            last = m.end();
        }
        sb.append(template, last, template.length());
        return sb.toString();
    }

    /**
     * 解析单个变量表达式：var 或 var:default
     */
    private String resolveVariable(String expr, PromptContext context) {
        int colonIdx = expr.indexOf(':');
        String varName;
        String defaultValue = null;
        if (colonIdx >= 0) {
            varName = expr.substring(0, colonIdx).trim();
            defaultValue = expr.substring(colonIdx + 1);
        } else {
            varName = expr;
        }

        Object v = context.get(varName);
        if (v == null) {
            return defaultValue != null ? defaultValue : "";
        }
        return v.toString();
    }

    /**
     * 判断值是否为"真值"（用于 #if 判断）
     */
    private boolean isTruthy(Object v) {
        if (v == null) return false;
        if (v instanceof Boolean) return (Boolean) v;
        if (v instanceof CharSequence) return ((CharSequence) v).length() > 0;
        if (v instanceof Number) return ((Number) v).doubleValue() != 0;
        if (v instanceof List) return !((List<?>) v).isEmpty();
        if (v instanceof Map) return !((Map<?, ?>) v).isEmpty();
        return true;
    }

    /**
     * 提取模板中引用的所有变量名（不含 #if/#each 控制变量，仅 ${var} 形式）
     * <p>
     * 用于在 PromptDefinition 中声明 variables，便于文档展示和 IDE 自动补全。
     * </p>
     */
    public List<String> extractVariables(String template) {
        List<String> vars = new ArrayList<>();
        if (template == null) return vars;
        Matcher m = VAR_PATTERN.matcher(template);
        while (m.find()) {
            String expr = m.group(1).trim();
            int colonIdx = expr.indexOf(':');
            String varName = (colonIdx >= 0 ? expr.substring(0, colonIdx) : expr).trim();
            if (!varName.isEmpty() && !vars.contains(varName)) {
                vars.add(varName);
            }
        }
        return vars;
    }
}
