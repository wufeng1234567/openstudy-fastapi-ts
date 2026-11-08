package com.deepseek.llm.proxy.persistence.browser;

import java.util.Map;

/**
 * 浏览器存储返回结果
 */
public class BrowserStorageResult {

    /** 关联的任务 ID */
    private String taskId;
    /** 是否成功 */
    private boolean success;
    /** 错误码（失败时） */
    private String errorCode;
    /** 错误消息（失败时） */
    private String errorMessage;
    /** 返回数据（JSON 字符串） */
    private String dataJson;
    /** 元数据 */
    private Map<String, Object> metadata;

    public BrowserStorageResult() {
    }

    public static BrowserStorageResult success(String taskId, String dataJson) {
        BrowserStorageResult r = new BrowserStorageResult();
        r.taskId = taskId;
        r.success = true;
        r.dataJson = dataJson;
        return r;
    }

    public static BrowserStorageResult failure(String taskId, String errorCode, String errorMessage) {
        BrowserStorageResult r = new BrowserStorageResult();
        r.taskId = taskId;
        r.success = false;
        r.errorCode = errorCode;
        r.errorMessage = errorMessage;
        return r;
    }

    public String getTaskId() { return taskId; }
    public void setTaskId(String taskId) { this.taskId = taskId; }
    public boolean isSuccess() { return success; }
    public void setSuccess(boolean success) { this.success = success; }
    public String getErrorCode() { return errorCode; }
    public void setErrorCode(String errorCode) { this.errorCode = errorCode; }
    public String getErrorMessage() { return errorMessage; }
    public void setErrorMessage(String errorMessage) { this.errorMessage = errorMessage; }
    public String getDataJson() { return dataJson; }
    public void setDataJson(String dataJson) { this.dataJson = dataJson; }
    public Map<String, Object> getMetadata() { return metadata; }
    public void setMetadata(Map<String, Object> metadata) { this.metadata = metadata; }
}
