package com.deepseek.llm.proxy.core.model;

import com.deepseek.llm.proxy.core.enums.Phase;

/**
 * 解析后的流式数据（BrowserExtensionProvider.parseChunk 返回）
 */
public class ParsedStream {

    /** 增量文本（已去除累积部分） */
    private String delta;
    /** 当前阶段 */
    private Phase phase;
    /** 累积全文（可选，用于校验） */
    private String cumulative;
    /** 原始 chunk 内容 */
    private String raw;

    public ParsedStream() {
    }

    public ParsedStream(String delta, Phase phase) {
        this.delta = delta;
        this.phase = phase;
    }

    public String getDelta() { return delta; }
    public void setDelta(String delta) { this.delta = delta; }
    public Phase getPhase() { return phase; }
    public void setPhase(Phase phase) { this.phase = phase; }
    public String getCumulative() { return cumulative; }
    public void setCumulative(String cumulative) { this.cumulative = cumulative; }
    public String getRaw() { return raw; }
    public void setRaw(String raw) { this.raw = raw; }
}
