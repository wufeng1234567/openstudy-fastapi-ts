package com.deepseek.llm.proxy.core.callback;

import com.deepseek.llm.proxy.core.exception.LlmProxyException;
import com.deepseek.llm.proxy.core.model.OcrResponse;

/**
 * OCR 回调
 */
public interface OcrCallback {

    /**
     * 流式增量（OCR 通常为单次返回，此方法可不实现）
     */
    default void onChunk(String delta) {}

    /**
     * 深度思考增量
     */
    default void onThinking(String delta) {}

    /**
     * OCR 完成
     */
    default void onComplete(OcrResponse response) {}

    /**
     * 错误回调
     */
    default void onError(LlmProxyException e) {}
}
