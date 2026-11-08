package com.deepseek.llm.proxy.persistence.browser;

import java.util.Map;

/**
 * 浏览器存储任务载荷
 * <p>
 * 后端通过此对象描述一个浏览器存储任务，由扩展 JS 端的 PersistenceAdapter 实际执行。
 * 后端不直接操作 IndexedDB，而是下发任务给扩展执行。
 * </p>
 */
public class BrowserStorageTask {

    /** 任务 ID */
    private String taskId;
    /** 操作类型：init / save-conversation / load-conversation / list-conversations
     *          / delete-conversation / save-memory / load-memory / clear-memory / destroy / health */
    private String operation;
    /** 数据载荷（JSON 字符串） */
    private String payloadJson;
    /** 额外参数 */
    private Map<String, Object> params;

    public BrowserStorageTask() {
    }

    public BrowserStorageTask(String taskId, String operation, String payloadJson) {
        this.taskId = taskId;
        this.operation = operation;
        this.payloadJson = payloadJson;
    }

    public String getTaskId() { return taskId; }
    public void setTaskId(String taskId) { this.taskId = taskId; }
    public String getOperation() { return operation; }
    public void setOperation(String operation) { this.operation = operation; }
    public String getPayloadJson() { return payloadJson; }
    public void setPayloadJson(String payloadJson) { this.payloadJson = payloadJson; }
    public Map<String, Object> getParams() { return params; }
    public void setParams(Map<String, Object> params) { this.params = params; }
}
