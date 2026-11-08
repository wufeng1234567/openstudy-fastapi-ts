package com.deepseek.llm.proxy.server.prompt;

import com.deepseek.llm.proxy.core.prompt.PromptContext;
import com.deepseek.llm.proxy.core.prompt.PromptDefinition;
import com.deepseek.llm.proxy.core.prompt.PromptException;
import com.deepseek.llm.proxy.core.prompt.PromptRegistry;
import com.deepseek.llm.proxy.core.prompt.PromptTemplate;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 默认 PromptRegistry 实现
 * <p>
 * 启动时通过 {@link ClasspathPromptLoader} 加载 classpath 下的提示词模板，
 * 同时支持运行时通过 {@link #register(PromptTemplate)} 注册新模板。
 * </p>
 */
public class DefaultPromptRegistry implements PromptRegistry {

    private static final Logger log = LoggerFactory.getLogger(DefaultPromptRegistry.class);

    /** 全局索引：promptId → template（按 id 直接查找） */
    private final Map<String, PromptTemplate> byId = new ConcurrentHashMap<>();

    /** 复合索引：(providerId + ":" + scene) → template */
    private final Map<String, PromptTemplate> byProviderScene = new ConcurrentHashMap<>();

    private final ClasspathPromptLoader loader;
    private final PromptTemplateEngine engine;

    public DefaultPromptRegistry(ClasspathPromptLoader loader) {
        this.loader = loader;
        this.engine = loader.getEngine();
        reload();
    }

    @Override
    public PromptTemplate get(String promptId) {
        return byId.get(promptId);
    }

    @Override
    public PromptTemplate get(String providerId, String scene) {
        // 先查 provider 专属
        if (providerId != null) {
            PromptTemplate t = byProviderScene.get(providerId + ":" + scene);
            if (t != null) return t;
        }
        // 降级到 _global
        return byProviderScene.get("_global:" + scene);
    }

    @Override
    public List<PromptTemplate> list() {
        List<PromptTemplate> all = new ArrayList<>(byId.values());
        return Collections.unmodifiableList(all);
    }

    @Override
    public void register(PromptTemplate template) {
        if (template == null || template.getDefinition() == null) {
            throw new IllegalArgumentException("template and definition must not be null");
        }
        PromptDefinition def = template.getDefinition();
        byId.put(def.getId(), template);
        String providerKey = def.getProviderId() == null ? "_global" : def.getProviderId();
        byProviderScene.put(providerKey + ":" + def.getScene(), template);
        log.info("已注册提示词模板: id={}, provider={}, scene={}",
                def.getId(), def.getProviderId(), def.getScene());
    }

    @Override
    public synchronized void reload() throws PromptException {
        log.info("开始加载提示词模板（classpath: {}）", loader.getClasspathLocation());

        List<PromptDefinition> defs = loader.load();
        // 清空旧索引（运行时注册的也会被清空，需要重新加载）
        byId.clear();
        byProviderScene.clear();

        for (PromptDefinition def : defs) {
            PromptTemplate template = new DefaultPromptTemplate(def, engine, loader);
            register(template);
        }
        log.info("提示词模板加载完成，共 {} 个", byId.size());
    }

    /**
     * 默认 PromptTemplate 实现：使用 PromptTemplateEngine 渲染
     */
    private static class DefaultPromptTemplate implements PromptTemplate {

        private final PromptDefinition definition;
        private final PromptTemplateEngine engine;
        private final ClasspathPromptLoader loader;

        DefaultPromptTemplate(PromptDefinition definition, PromptTemplateEngine engine, ClasspathPromptLoader loader) {
            this.definition = definition;
            this.engine = engine;
            this.loader = loader;
        }

        @Override
        public PromptDefinition getDefinition() {
            return definition;
        }

        @Override
        public String render(PromptContext context) throws PromptException {
            // 设置 include 解析器，支持 ${#include "xxx.txt"}
            PromptTemplateEngine.IncludeResolver resolver = loader::loadSharedFragment;
            PromptTemplateEngine engineWithInclude = new PromptTemplateEngine(resolver);
            return engineWithInclude.render(definition.getContent(), context);
        }
    }
}
