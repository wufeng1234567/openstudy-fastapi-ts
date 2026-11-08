package com.deepseek.llm.proxy.ext.deepseek;

import com.deepseek.llm.proxy.core.BrowserExtensionProvider;
import com.deepseek.llm.proxy.core.enums.Capability;
import com.deepseek.llm.proxy.core.enums.Phase;
import com.deepseek.llm.proxy.core.enums.ProviderMode;
import com.deepseek.llm.proxy.core.model.ChatRequest;
import com.deepseek.llm.proxy.core.model.DomSelectors;
import com.deepseek.llm.proxy.core.model.ParsedStream;
import com.deepseek.llm.proxy.core.model.TaskPayload;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * DeepSeek 网页版 Provider 实现
 * <p>
 * 还原现有 DS 插件行为（D:\OpenStudy\deepseek-proxy\extension\）：
 * <ul>
 *   <li>host pattern: https://chat.deepseek.com/*</li>
 *   <li>拦截器路径: providers/deepseek/interceptor.js</li>
 *   <li>DOM 选择器: textarea/.ds-toggle-button/[role=radio][data-model-type]</li>
 *   <li>chunk 解析: OT fragments 格式（非 OpenAI 风格）</li>
 *   <li>支持模式: default/expert/vision</li>
 *   <li>能力: STREAMING/THINKING/IMAGES/FILES/MODES/TOOLS/MEMORY</li>
 * </ul>
 * </p>
 */
public class DeepSeekProvider implements BrowserExtensionProvider {

    private static final Logger log = LoggerFactory.getLogger(DeepSeekProvider.class);

    @Override
    public String getId() {
        return DeepSeekProviderConstants.ID;
    }

    @Override
    public String getDisplayName() {
        return DeepSeekProviderConstants.DISPLAY_NAME;
    }

    @Override
    public Set<Capability> getCapabilities() {
        return DeepSeekProviderConstants.CAPABILITIES;
    }

    @Override
    public List<ProviderMode> getSupportedModes() {
        return DeepSeekProviderConstants.SUPPORTED_MODES;
    }

    @Override
    public String getInterceptorScriptPath() {
        return DeepSeekProviderConstants.INTERCEPTOR_SCRIPT_PATH;
    }

    @Override
    public String getHostPattern() {
        return DeepSeekProviderConstants.HOST_PATTERN;
    }

    @Override
    public String getLoginUrl() {
        return DeepSeekProviderConstants.LOGIN_URL;
    }

    @Override
    public DomSelectors getDomSelectors() {
        DomSelectors selectors = new DomSelectors();
        selectors.setInput(DeepSeekProviderConstants.SEL_INPUT);
        selectors.setSendButton(DeepSeekProviderConstants.SEL_SEND_BUTTON);
        selectors.setDeepThinkToggle(DeepSeekProviderConstants.SEL_DEEP_THINK_TOGGLE);
        selectors.setModeRadio(DeepSeekProviderConstants.SEL_MODE_RADIO);
        selectors.setFileInput(DeepSeekProviderConstants.SEL_FILE_INPUT);
        Map<String, String> extras = new HashMap<>();
        extras.put("loginForm", DeepSeekProviderConstants.SEL_LOGIN_FORM);
        extras.put("avatar", DeepSeekProviderConstants.SEL_AVATAR);
        selectors.setExtraSelectors(extras);
        return selectors;
    }

    /**
     * 把通用 ChatRequest 序列化为扩展任务载荷
     * <p>
     * DS 网页版无 system role，systemPrompt 与 history 拼到 content 前。
     * 扩展端 background.js 的 injectedTriggerHandler 接收此载荷并执行：
     * <ol>
     *   <li>找到 DS 输入框，insertText 注入 content</li>
     *   <li>如有 images：构造 DataTransfer 触发 file input change</li>
     *   <li>如有 files：触发对应 accept 类型的 file input</li>
     *   <li>如有 enableThinking：定位 .ds-toggle-button 切换深度思考开关</li>
     *   <li>如有 mode：点击对应 data-model-type 的 radio</li>
     *   <li>触发 Enter 键提交</li>
     * </ol>
     * </p>
     */
    @Override
    public TaskPayload serializeTask(ChatRequest request) {
        TaskPayload payload = new TaskPayload();
        payload.setType(DeepSeekProviderConstants.TASK_TYPE_CHAT);
        payload.setContent(assembleContent(request));

        // 图片
        if (request.getImages() != null && !request.getImages().isEmpty()) {
            payload.setImages(request.getImages().stream()
                    .map(img -> img.getDataUrl())
                    .toList());
        }

        // 文件
        if (request.getFiles() != null && !request.getFiles().isEmpty()) {
            List<Map<String, String>> files = request.getFiles().stream()
                    .map(f -> {
                        Map<String, String> m = new HashMap<>();
                        m.put("name", f.getName());
                        m.put("dataUrl", f.getDataUrl());
                        m.put("mimeType", f.getMimeType());
                        return m;
                    })
                    .toList();
            payload.setFiles(files);
        }

        payload.setEnableThinking(request.getEnableThinking());
        payload.setMode(request.getMode());
        // DS 网页版无 enableMemory 概念：true=新会话（不沿用历史）/false=沿用
        payload.setNewSession(request.getEnableMemory() == null ? null : !request.getEnableMemory());

        log.debug("DS 任务已序列化：images={}, files={}, thinking={}, mode={}, newSession={}",
                payload.getImages() != null ? payload.getImages().size() : 0,
                payload.getFiles() != null ? payload.getFiles().size() : 0,
                payload.getEnableThinking(), payload.getMode(), payload.getNewSession());
        return payload;
    }

    /**
     * 解析扩展回传的 chunk
     * <p>
     * DS 网页版 SSE 数据采用 OT (Operational Transformation) fragments 模型，
     * <b>不是</b> OpenAI 风格的 choices[0].delta。
     * 扩展端 interceptor.js 已将 SSE 解析为统一的 chunk 格式回传：
     * <pre>
     * {
     *   "content": "累积全文",
     *   "reasoning": "累积思考全文"（thinking 阶段才有）,
     *   "phase": "thinking" | "response",
     *   "taskId": "..."
     * }
     * </pre>
     * </p>
     * <p>
     * 这里只需识别 phase 并提取 delta（扩展端已处理 OT fragments → 累积全文转换）。
     * </p>
     *
     * @param rawChunk 扩展回传的原始 JSON 字符串
     * @param phase    当前阶段（与 chunk 中 phase 应一致，作为兜底）
     */
    @Override
    public ParsedStream parseChunk(String rawChunk, Phase phase) {
        if (rawChunk == null || rawChunk.isEmpty()) {
            return new ParsedStream("", phase);
        }

        // 扩展端回传的是 JSON：{"content":"...","reasoning":"...","phase":"...","taskId":"..."}
        try {
            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            var node = mapper.readTree(rawChunk);

            String phaseStr = node.has("phase") ? node.get("phase").asText() : null;
            Phase actualPhase = "thinking".equalsIgnoreCase(phaseStr) ? Phase.THINKING :
                    "response".equalsIgnoreCase(phaseStr) ? Phase.RESPONSE : phase;

            String content;
            if (actualPhase == Phase.THINKING) {
                content = node.has("reasoning") ? node.get("reasoning").asText() :
                        (node.has("content") ? node.get("content").asText() : "");
            } else {
                content = node.has("content") ? node.get("content").asText() :
                        (node.has("reasoning") ? node.get("reasoning").asText() : "");
            }

            ParsedStream parsed = new ParsedStream(content, actualPhase);
            parsed.setCumulative(content);  // 扩展回传的是累积全文
            parsed.setRaw(rawChunk);
            return parsed;
        } catch (Exception e) {
            log.warn("DS chunk 解析失败，按裸文本处理：{}", e.getMessage());
            // 兜底：按裸文本处理
            ParsedStream parsed = new ParsedStream(rawChunk, phase);
            parsed.setRaw(rawChunk);
            return parsed;
        }
    }

    /**
     * DS 网页版无 system role，把 systemPrompt + history 拼到 content 前
     * <p>与现有项目 ds-proxy.js 的拼接逻辑保持一致。</p>
     */
    private String assembleContent(ChatRequest request) {
        StringBuilder sb = new StringBuilder();
        if (request.getSystemPrompt() != null && !request.getSystemPrompt().isEmpty()) {
            sb.append(request.getSystemPrompt()).append("\n\n");
        }
        if (request.getHistory() != null && !request.getHistory().isEmpty()) {
            sb.append("## 历史对话\n\n");
            for (var msg : request.getHistory()) {
                sb.append("**").append(msg.getRole()).append("**: ")
                  .append(msg.getContent() != null ? msg.getContent() : "")
                  .append("\n\n");
            }
        }
        sb.append("## 用户消息\n\n").append(request.getContent());
        return sb.toString();
    }
}
