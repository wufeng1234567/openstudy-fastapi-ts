package com.deepseek.llm.proxy.server.prompt;

import com.deepseek.llm.proxy.core.prompt.PromptDefinition;
import com.deepseek.llm.proxy.core.prompt.PromptException;
import com.deepseek.llm.proxy.core.prompt.PromptManager;
import com.deepseek.llm.proxy.core.prompt.PromptTemplate;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 提示词管理 REST 端点
 * <p>
 * 让接入方可以：
 * <ul>
 *   <li>列出所有可用提示词（含变量声明）</li>
 *   <li>查看指定提示词的完整内容</li>
 *   <li>预渲染提示词（传入变量测试效果）</li>
 *   <li>触发热加载</li>
 * </ul>
 * </p>
 */
@RestController
@RequestMapping("/api/v1/llm-proxy/prompts")
public class PromptController {

    private static final Logger log = LoggerFactory.getLogger(PromptController.class);

    private final PromptManager promptManager;

    public PromptController(PromptManager promptManager) {
        this.promptManager = promptManager;
    }

    /**
     * 列出所有提示词
     * <p>GET /api/v1/llm-proxy/prompts</p>
     */
    @GetMapping
    public ResponseEntity<List<Map<String, Object>>> list() {
        List<Map<String, Object>> result = new ArrayList<>();
        for (PromptTemplate t : promptManager.list()) {
            result.add(toSummary(t));
        }
        return ResponseEntity.ok(result);
    }

    /**
     * 查看指定提示词详情（含模板原文）
     * <p>GET /api/v1/llm-proxy/prompts/{id}</p>
     */
    @GetMapping("/{id}")
    public ResponseEntity<?> get(@PathVariable String id) {
        PromptTemplate t = promptManager.getRegistry().get(id);
        if (t == null) {
            return ResponseEntity.status(404).body(Map.of(
                    "code", "PROMPT_NOT_FOUND",
                    "message", "提示词不存在: " + id
            ));
        }
        return ResponseEntity.ok(toDetail(t));
    }

    /**
     * 按 Provider + 场景查找
     * <p>GET /api/v1/llm-proxy/prompts/providers/{providerId}/scenes/{scene}</p>
     */
    @GetMapping("/providers/{providerId}/scenes/{scene}")
    public ResponseEntity<?> getByProviderScene(@PathVariable String providerId, @PathVariable String scene) {
        PromptTemplate t = promptManager.getRegistry().get(providerId, scene);
        if (t == null) {
            return ResponseEntity.status(404).body(Map.of(
                    "code", "PROMPT_NOT_FOUND",
                    "message", "未找到 provider=" + providerId + " scene=" + scene + " 的提示词"
            ));
        }
        return ResponseEntity.ok(toDetail(t));
    }

    /**
     * 预渲染提示词（接入方测试用）
     * <p>POST /api/v1/llm-proxy/prompts/{id}/render</p>
     * <p>Body: {"variables": {...}}</p>
     */
    @PostMapping("/{id}/render")
    public ResponseEntity<?> render(@PathVariable String id, @RequestBody Map<String, Object> body) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> variables = body == null ? null : (Map<String, Object>) body.get("variables");
            String rendered = promptManager.render(id, variables);
            return ResponseEntity.ok(Map.of(
                    "promptId", id,
                    "rendered", rendered,
                    "length", rendered.length()
            ));
        } catch (PromptException e) {
            log.warn("渲染提示词失败: id={}, err={}", id, e.getMessage());
            return ResponseEntity.badRequest().body(Map.of(
                    "code", "RENDER_FAILED",
                    "message", e.getMessage()
            ));
        }
    }

    /**
     * 触发热加载（重新扫描 classpath 和外部目录）
     * <p>POST /api/v1/llm-proxy/prompts/reload</p>
     */
    @PostMapping("/reload")
    public ResponseEntity<?> reload() {
        try {
            promptManager.reload();
            int count = promptManager.list().size();
            log.info("提示词热加载完成，共 {} 个", count);
            return ResponseEntity.ok(Map.of(
                    "ok", true,
                    "count", count,
                    "message", "热加载完成"
            ));
        } catch (PromptException e) {
            log.error("提示词热加载失败", e);
            return ResponseEntity.internalServerError().body(Map.of(
                    "ok", false,
                    "code", "RELOAD_FAILED",
                    "message", e.getMessage()
            ));
        }
    }

    // ========== 内部转换工具 ==========

    private Map<String, Object> toSummary(PromptTemplate t) {
        PromptDefinition d = t.getDefinition();
        Map<String, Object> m = new HashMap<>();
        m.put("id", d.getId());
        m.put("providerId", d.getProviderId());
        m.put("scene", d.getScene());
        m.put("version", d.getVersion());
        m.put("variables", d.getVariables());
        m.put("description", d.getDescription());
        m.put("source", d.getSource());
        return m;
    }

    private Map<String, Object> toDetail(PromptTemplate t) {
        Map<String, Object> m = toSummary(t);
        m.put("content", t.getDefinition().getContent());
        return m;
    }
}
