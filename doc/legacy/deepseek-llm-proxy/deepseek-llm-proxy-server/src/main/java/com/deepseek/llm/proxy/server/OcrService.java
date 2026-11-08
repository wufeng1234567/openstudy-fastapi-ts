package com.deepseek.llm.proxy.server;

import com.deepseek.llm.proxy.core.LlmProvider;
import com.deepseek.llm.proxy.core.callback.OcrCallback;
import com.deepseek.llm.proxy.core.callback.StreamCallback;
import com.deepseek.llm.proxy.core.enums.Capability;
import com.deepseek.llm.proxy.core.enums.ErrorCode;
import com.deepseek.llm.proxy.core.enums.Phase;
import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import com.deepseek.llm.proxy.core.model.ChatRequest;
import com.deepseek.llm.proxy.core.model.FullResponse;
import com.deepseek.llm.proxy.core.model.ImageData;
import com.deepseek.llm.proxy.core.model.OcrRequest;
import com.deepseek.llm.proxy.core.model.OcrResponse;
import com.deepseek.llm.proxy.core.prompt.PromptManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * OCR 业务服务
 * <p>
 * OCR 本质是 chat + 图片 + 提示词的组合。
 * 把 OcrRequest 转换为 ChatRequest，复用 ChatService 完成实际调用，
 * 然后在 onComplete 中提取 OCR 结果（text 或 structured JSON）。
 * </p>
 * <p>
 * 提示词来源优先级：request.promptId &gt; request.prompt &gt; 默认模板（ocr-default / ocr-structured）
 * </p>
 */
public class OcrService {

    private static final Logger log = LoggerFactory.getLogger(OcrService.class);

    /** 默认 OCR 提示词（PromptManager 未配置时使用） */
    private static final String DEFAULT_OCR_PROMPT =
            "请提取图片中的所有文字内容，保持原始结构。只返回提取的文本，不要添加解释。";

    /** 结构化 OCR 提示词模板（PromptManager 未配置时使用） */
    private static final String STRUCTURED_OCR_PROMPT_TEMPLATE =
            "请提取图片中的内容并按以下 JSON Schema 返回结果，只返回 JSON，不要 markdown 代码块：\n%s";

    private final ChatService chatService;
    private final ProviderRegistry providerRegistry;
    private final long defaultTimeoutMs;
    /** 可选，未配置时使用硬编码默认提示词 */
    private final PromptManager promptManager;
    /** 默认 OCR 提示词 ID */
    private final String defaultOcrPromptId;
    /** 默认结构化 OCR 提示词 ID */
    private final String defaultOcrStructuredPromptId;

    public OcrService(ChatService chatService, ProviderRegistry providerRegistry, long defaultTimeoutMs) {
        this(chatService, providerRegistry, defaultTimeoutMs, null, "ocr-default", "ocr-structured");
    }

    public OcrService(ChatService chatService, ProviderRegistry providerRegistry, long defaultTimeoutMs,
                      PromptManager promptManager,
                      String defaultOcrPromptId,
                      String defaultOcrStructuredPromptId) {
        this.chatService = chatService;
        this.providerRegistry = providerRegistry;
        this.defaultTimeoutMs = defaultTimeoutMs;
        this.promptManager = promptManager;
        this.defaultOcrPromptId = defaultOcrPromptId;
        this.defaultOcrStructuredPromptId = defaultOcrStructuredPromptId;
    }

    /** 流式 OCR */
    public String ocr(OcrRequest request, OcrCallback callback) throws LlmProxyException {
        validateOcrRequest(request);
        LlmProvider provider = providerRegistry.require(request.getProviderId());
        if (!provider.supportsImages()) {
            throw new LlmProxyException(ErrorCode.UNSUPPORTED_FEATURE,
                    "Provider " + provider.getId() + " 不支持图片输入（OCR 依赖此能力）");
        }

        // 把 OcrRequest 转换为 ChatRequest
        ChatRequest chatReq = buildChatRequest(request, provider);

        StreamCallback streamCallback = new StreamCallback() {
            private final StringBuilder responseText = new StringBuilder();
            private final StringBuilder thinkingText = new StringBuilder();

            @Override
            public void onThinking(String delta) {
                thinkingText.append(delta);
                if (callback != null) callback.onThinking(delta);
            }

            @Override
            public void onChunk(String delta) {
                responseText.append(delta);
                if (callback != null) callback.onChunk(delta);
            }

            @Override
            public void onComplete(FullResponse response) {
                if (callback == null) return;
                try {
                    OcrResponse ocrResp = parseOcrResponse(response, request);
                    callback.onComplete(ocrResp);
                } catch (Exception e) {
                    callback.onError(new LlmProxyException(ErrorCode.INTERNAL_ERROR,
                            "OCR 结果解析失败：" + e.getMessage(), e));
                }
            }

            @Override
            public void onError(LlmProxyException e) {
                if (callback != null) callback.onError(e);
            }
        };

        return chatService.chat(chatReq, streamCallback);
    }

    /** 同步 OCR */
    public OcrResponse ocrSync(OcrRequest request) throws LlmProxyException {
        validateOcrRequest(request);
        LlmProvider provider = providerRegistry.require(request.getProviderId());
        if (!provider.supportsImages()) {
            throw new LlmProxyException(ErrorCode.UNSUPPORTED_FEATURE,
                    "Provider " + provider.getId() + " 不支持图片输入");
        }

        ChatRequest chatReq = buildChatRequest(request, provider);
        var chatResp = chatService.chatSync(chatReq);

        OcrResponse resp = new OcrResponse();
        resp.setRequestId(chatResp.getRequestId());
        resp.setCompletedAt(chatResp.getCompletedAt());
        String content = chatResp.getContent();
        if (Boolean.TRUE.equals(request.getStructured())) {
            Object structured = parseStructuredJson(content);
            resp.setText(content);
            resp.setStructuredData(structured);
        } else {
            resp.setText(content);
        }
        return resp;
    }

    private void validateOcrRequest(OcrRequest request) throws LlmProxyException {
        if (request == null) {
            throw new LlmProxyException(ErrorCode.INVALID_REQUEST, "request 不能为空");
        }
        if (request.getProviderId() == null || request.getProviderId().isEmpty()) {
            throw new LlmProxyException(ErrorCode.INVALID_REQUEST, "providerId 不能为空");
        }
        if (request.getImages() == null || request.getImages().isEmpty()) {
            throw new LlmProxyException(ErrorCode.INVALID_REQUEST, "images 不能为空");
        }
    }

    private ChatRequest buildChatRequest(OcrRequest request, LlmProvider provider) {
        String prompt = buildOcrPrompt(request);

        List<ImageData> images = request.getImages();
        // DS 网页版支持多图：所有图片作为一次 chat 请求的 images
        ChatRequest.Builder b = ChatRequest.builder()
                .providerId(provider.getId())
                .userId(request.getUserId())
                .tenantId(request.getTenantId())
                .content(prompt)
                .images(images)
                .enableThinking(request.getEnableThinking());

        long timeoutMs = request.getTimeoutMs() != null ? request.getTimeoutMs() : defaultTimeoutMs;
        b.timeoutMs(timeoutMs);

        // 识图模式下用 vision mode
        if (provider.getCapabilities().contains(Capability.MODES)) {
            b.mode("vision");
        }
        return b.build();
    }

    /**
     * 构建 OCR 提示词
     * <p>
     * 优先级：request.promptId &gt; request.prompt &gt; 默认模板（ocr-default / ocr-structured）
     * </p>
     */
    private String buildOcrPrompt(OcrRequest request) {
        // 1. promptId 优先（通过 PromptManager 渲染）
        if (request.getPromptId() != null && !request.getPromptId().isEmpty()) {
            if (promptManager != null) {
                try {
                    return promptManager.render(request.getPromptId(), request.getPromptVariables());
                } catch (Exception e) {
                    log.warn("渲染 OCR 提示词 promptId={} 失败，降级到 prompt 字段: {}",
                            request.getPromptId(), e.getMessage());
                }
            } else {
                log.warn("请求指定了 promptId={} 但 PromptManager 未配置，降级到 prompt 字段", request.getPromptId());
            }
        }

        // 2. 自定义 prompt 字段
        if (request.getPrompt() != null && !request.getPrompt().isEmpty()) {
            return request.getPrompt();
        }

        // 3. 默认模板（PromptManager 可用时）
        if (promptManager != null) {
            String defaultPromptId = Boolean.TRUE.equals(request.getStructured())
                    ? defaultOcrStructuredPromptId
                    : defaultOcrPromptId;
            if (defaultPromptId != null && !defaultPromptId.isEmpty()) {
                try {
                    Map<String, Object> vars = new HashMap<>();
                    if (request.getPromptVariables() != null) vars.putAll(request.getPromptVariables());
                    if (request.getExpectedSchemaJson() != null) {
                        vars.put("schema", request.getExpectedSchemaJson());
                    }
                    return promptManager.render(defaultPromptId, vars);
                } catch (Exception e) {
                    log.warn("默认 OCR 提示词 {} 渲染失败，降级到硬编码: {}", defaultPromptId, e.getMessage());
                }
            }
        }

        // 4. 硬编码兜底（PromptManager 未配置时）
        if (Boolean.TRUE.equals(request.getStructured())) {
            if (request.getExpectedSchemaJson() != null) {
                return String.format(STRUCTURED_OCR_PROMPT_TEMPLATE, request.getExpectedSchemaJson());
            }
            return "请提取图片内容并以 JSON 格式返回，只返回 JSON，不要 markdown 代码块。";
        }
        return DEFAULT_OCR_PROMPT;
    }

    private OcrResponse parseOcrResponse(FullResponse response, OcrRequest request) {
        OcrResponse resp = new OcrResponse();
        resp.setRequestId(response.getRequestId());
        resp.setCompletedAt(response.getCompletedAt());
        String content = response.getContent();
        if (Boolean.TRUE.equals(request.getStructured())) {
            Object structured = parseStructuredJson(content);
            resp.setText(content);
            resp.setStructuredData(structured);
        } else {
            resp.setText(content);
        }
        return resp;
    }

    /** 尝试从 markdown 代码块或裸 JSON 中提取结构化数据 */
    private Object parseStructuredJson(String content) {
        if (content == null || content.isEmpty()) return null;
        String trimmed = content.trim();
        // 去除 markdown 围栏
        if (trimmed.startsWith("```")) {
            int firstNewline = trimmed.indexOf('\n');
            if (firstNewline > 0) {
                trimmed = trimmed.substring(firstNewline + 1);
            }
            if (trimmed.endsWith("```")) {
                trimmed = trimmed.substring(0, trimmed.length() - 3);
            }
            trimmed = trimmed.trim();
        }
        try {
            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            return mapper.readValue(trimmed, Object.class);
        } catch (Exception e) {
            log.warn("OCR 结构化解析失败，返回原始文本：{}", e.getMessage());
            return null;
        }
    }
}
