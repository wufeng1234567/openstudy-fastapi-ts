package com.deepseek.llm.proxy.core.model;

import java.time.Instant;

/**
 * OCR 响应
 */
public class OcrResponse {

    private String requestId;
    /** 纯文本结果 */
    private String text;
    /** 结构化数据（structured=true 时填充） */
    private Object structuredData;
    /** 完成时间 */
    private Instant completedAt;

    public String getRequestId() { return requestId; }
    public void setRequestId(String requestId) { this.requestId = requestId; }
    public String getText() { return text; }
    public void setText(String text) { this.text = text; }
    public Object getStructuredData() { return structuredData; }
    public void setStructuredData(Object structuredData) { this.structuredData = structuredData; }
    public Instant getCompletedAt() { return completedAt; }
    public void setCompletedAt(Instant completedAt) { this.completedAt = completedAt; }

    /** 转换为目标类型（需调用方自行反序列化） */
    @SuppressWarnings("unchecked")
    public <T> T to(Class<T> clazz) {
        if (structuredData == null) {
            return null;
        }
        if (clazz.isInstance(structuredData)) {
            return (T) structuredData;
        }
        throw new ClassCastException("无法将 " + structuredData.getClass() + " 转换为 " + clazz);
    }
}
