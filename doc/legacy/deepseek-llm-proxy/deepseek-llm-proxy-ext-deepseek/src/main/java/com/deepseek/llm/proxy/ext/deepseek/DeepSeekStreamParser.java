package com.deepseek.llm.proxy.ext.deepseek;

import com.deepseek.llm.proxy.core.enums.Phase;
import com.deepseek.llm.proxy.core.model.ParsedStream;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.HashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * DeepSeek SSE chunk 解析器（OT fragments 格式）
 * <p>
 * 还原 D:\OpenStudy\deepseek-proxy\extension\content\interceptor.js 的 extractDelta 逻辑。
 * 此解析器在 Java 端（服务端）使用，用于扩展未拦截场景下的备用解析，
 * 或用于将原始 DS SSE 流直接转 SDK 标准格式（不依赖扩展）。
 * </p>
 * <p>
 * <b>数据格式优先级</b>（与 interceptor.js extractDelta 对齐）：
 * <ol>
 *   <li>OT APPEND: {p:"response/fragments", o:"APPEND", v:[{type:"THINK"|"RESPONSE", content:"..."}]}</li>
 *   <li>OT 增量更新: {p:"response/fragments/-1/content", v:"增量文本"}</li>
 *   <li>Snapshot: {v:{response:{fragments:[{type:"THINK",content:"..."},...]}}}</li>
 *   <li>裸字符串: {v:"增量文本"}</li>
 * </ol>
 * </p>
 */
public class DeepSeekStreamParser {

    private static final Logger log = LoggerFactory.getLogger(DeepSeekStreamParser.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private static final Pattern FRAGMENT_PATH_PATTERN =
            Pattern.compile("response/fragments/(-?\\d+)");

    private final Map<Integer, FragmentType> fragmentTypes = new HashMap<>();
    private final StringBuilder thinkingCumulative = new StringBuilder();
    private final StringBuilder responseCumulative = new StringBuilder();
    private String currentMode = "response";

    public enum FragmentType { THINK, RESPONSE }

    /**
     * 解析单个 SSE 数据行（已去除 "data: " 前缀的 JSON 字符串）
     * <p>SSE 结束信号 [DONE] 返回 phase=RESPONSE 的空 ParsedStream（isTerminal=false）。</p>
     */
    public ParsedStream parse(String dataLine) {
        if (dataLine == null || dataLine.isEmpty()) {
            return new ParsedStream("", Phase.RESPONSE);
        }
        String trimmed = dataLine.trim();
        if ("[DONE]".equals(trimmed)) {
            // SSE 结束：返回空，由调用方判断 sendDone
            ParsedStream ps = new ParsedStream("", Phase.RESPONSE);
            ps.setRaw(trimmed);
            return ps;
        }

        try {
            JsonNode root = MAPPER.readTree(trimmed);
            return extractDelta(root);
        } catch (Exception e) {
            log.debug("非 JSON 数据行，按裸文本处理：{}", trimmed);
            ParsedStream ps = new ParsedStream(trimmed, Phase.RESPONSE);
            ps.setRaw(trimmed);
            return ps;
        }
    }

    /** 获取累积思考全文 */
    public String getThinkingCumulative() {
        return thinkingCumulative.toString();
    }

    /** 获取累积回复全文 */
    public String getResponseCumulative() {
        return responseCumulative.toString();
    }

    /** 重置状态（每个任务开始前调用） */
    public void reset() {
        fragmentTypes.clear();
        thinkingCumulative.setLength(0);
        responseCumulative.setLength(0);
        currentMode = "response";
    }

    private ParsedStream extractDelta(JsonNode data) {
        // 1. OT APPEND 事件：{p:"response/fragments", o:"APPEND", v:[...]}
        if (data.has("p") && "response/fragments".equals(data.get("p").asText())
                && data.has("o") && "APPEND".equals(data.get("o").asText())) {
            return handleOtAppend(data.get("v"));
        }

        // 2. OT 增量更新：{p:"response/fragments/-1/content", v:"..."}
        if (data.has("p")) {
            String path = data.get("p").asText();
            Matcher m = FRAGMENT_PATH_PATTERN.matcher(path);
            if (m.find() && path.contains("/content")) {
                return handleOtUpdate(m.group(1), data.get("v"));
            }
        }

        // 3. Snapshot 事件：{v:{response:{fragments:[...]}}}
        if (data.has("v") && data.get("v").isObject()
                && data.get("v").has("response")
                && data.get("v").get("response").has("fragments")) {
            return handleSnapshot(data.get("v").get("response").get("fragments"));
        }

        // 4. 裸字符串 delta：{v:"增量文本"}
        if (data.has("v") && data.get("v").isTextual()) {
            return handleBareString(data.get("v").asText());
        }

        // 兜底
        log.debug("未知 DS 数据格式：{}", data);
        ParsedStream ps = new ParsedStream("", Phase.RESPONSE);
        return ps;
    }

    private ParsedStream handleOtAppend(JsonNode vArray) {
        if (vArray == null || !vArray.isArray()) {
            return new ParsedStream("", Phase.RESPONSE);
        }
        for (JsonNode frag : vArray) {
            String type = frag.has("type") ? frag.get("type").asText() : "RESPONSE";
            String content = frag.has("content") ? frag.get("content").asText() : "";
            int idx = fragmentTypes.size();
            FragmentType ft = "THINK".equalsIgnoreCase(type) ? FragmentType.THINK : FragmentType.RESPONSE;
            fragmentTypes.put(idx, ft);
            if (ft == FragmentType.THINK) {
                thinkingCumulative.append(content);
            } else {
                responseCumulative.append(content);
            }
        }
        // 返回累积全文（与 interceptor.js 行为一致）
        String cumulative = thinkingCumulative.length() > 0
                ? thinkingCumulative.toString()
                : responseCumulative.toString();
        Phase phase = thinkingCumulative.length() > 0 ? Phase.THINKING : Phase.RESPONSE;
        ParsedStream ps = new ParsedStream(cumulative, phase);
        ps.setCumulative(cumulative);
        return ps;
    }

    private ParsedStream handleOtUpdate(String idxStr, JsonNode v) {
        if (v == null || !v.isTextual()) {
            return new ParsedStream("", Phase.RESPONSE);
        }
        String delta = v.asText();
        int idx;
        try {
            idx = Integer.parseInt(idxStr);
        } catch (NumberFormatException e) {
            idx = fragmentTypes.size() - 1;
        }
        // 负数索引（DS 用 -1 表示最新追加的 fragment）
        if (idx < 0) {
            idx = fragmentTypes.size() + idx;
        }
        FragmentType ft = fragmentTypes.getOrDefault(idx, FragmentType.RESPONSE);
        if (ft == FragmentType.THINK) {
            thinkingCumulative.append(delta);
            currentMode = "thinking";
        } else {
            responseCumulative.append(delta);
            currentMode = "response";
        }
        String cumulative = ft == FragmentType.THINK
                ? thinkingCumulative.toString()
                : responseCumulative.toString();
        Phase phase = ft == FragmentType.THINK ? Phase.THINKING : Phase.RESPONSE;
        ParsedStream ps = new ParsedStream(cumulative, phase);
        ps.setCumulative(cumulative);
        return ps;
    }

    private ParsedStream handleSnapshot(JsonNode fragments) {
        if (fragments == null || !fragments.isArray()) {
            return new ParsedStream("", Phase.RESPONSE);
        }
        // Snapshot 模式：重建 fragmentTypes 并重新累积
        fragmentTypes.clear();
        thinkingCumulative.setLength(0);
        responseCumulative.setLength(0);
        int idx = 0;
        for (JsonNode frag : fragments) {
            String type = frag.has("type") ? frag.get("type").asText() : "RESPONSE";
            String content = frag.has("content") ? frag.get("content").asText() : "";
            FragmentType ft = "THINK".equalsIgnoreCase(type) ? FragmentType.THINK : FragmentType.RESPONSE;
            fragmentTypes.put(idx++, ft);
            if (ft == FragmentType.THINK) {
                thinkingCumulative.append(content);
            } else {
                responseCumulative.append(content);
            }
        }
        String cumulative = thinkingCumulative.length() > 0
                ? thinkingCumulative.toString()
                : responseCumulative.toString();
        Phase phase = thinkingCumulative.length() > 0 ? Phase.THINKING : Phase.RESPONSE;
        ParsedStream ps = new ParsedStream(cumulative, phase);
        ps.setCumulative(cumulative);
        return ps;
    }

    private ParsedStream handleBareString(String delta) {
        // 裸字符串：用 currentMode 判断 phase
        Phase phase = "thinking".equals(currentMode) ? Phase.THINKING : Phase.RESPONSE;
        if (phase == Phase.THINKING) {
            thinkingCumulative.append(delta);
        } else {
            responseCumulative.append(delta);
        }
        String cumulative = phase == Phase.THINKING
                ? thinkingCumulative.toString()
                : responseCumulative.toString();
        ParsedStream ps = new ParsedStream(cumulative, phase);
        ps.setCumulative(cumulative);
        return ps;
    }

    /**
     * 清理内容（与 interceptor.js cleanContent 对齐）
     * <p>去除 FINISHED$ 标记，识别代码语言自动补围栏。</p>
     */
    public static String cleanContent(String content) {
        if (content == null) return "";
        // 去除 FINISHED$ 标记
        String cleaned = content.replace("FINISHED$", "");
        return cleaned;
    }
}
