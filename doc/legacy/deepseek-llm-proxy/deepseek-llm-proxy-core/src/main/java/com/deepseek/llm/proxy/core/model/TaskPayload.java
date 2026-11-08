package com.deepseek.llm.proxy.core.model;

import java.util.Map;

/**
 * 扩展任务载荷（BrowserExtensionProvider.serializeTask 返回）
 * <p>序列化后的任务载荷会下发给浏览器扩展执行。</p>
 */
public class TaskPayload {

    /** 任务 ID */
    private String taskId;
    /** 任务类型：chat / ocr */
    private String type;
    /** 完整文本内容（含系统提示词拼接） */
    private String content;
    /** 图片列表（base64 data URL） */
    private java.util.List<String> images;
    /** 文件列表（base64 data URL + 文件名） */
    private java.util.List<Map<String, String>> files;
    /** 是否开启深度思考 */
    private Boolean enableThinking;
    /** 对话模式 */
    private String mode;
    /** 是否新会话 */
    private Boolean newSession;

    public String getTaskId() { return taskId; }
    public void setTaskId(String taskId) { this.taskId = taskId; }
    public String getType() { return type; }
    public void setType(String type) { this.type = type; }
    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }
    public java.util.List<String> getImages() { return images; }
    public void setImages(java.util.List<String> images) { this.images = images; }
    public java.util.List<Map<String, String>> getFiles() { return files; }
    public void setFiles(java.util.List<Map<String, String>> files) { this.files = files; }
    public Boolean getEnableThinking() { return enableThinking; }
    public void setEnableThinking(Boolean enableThinking) { this.enableThinking = enableThinking; }
    public String getMode() { return mode; }
    public void setMode(String mode) { this.mode = mode; }
    public Boolean getNewSession() { return newSession; }
    public void setNewSession(Boolean newSession) { this.newSession = newSession; }
}
