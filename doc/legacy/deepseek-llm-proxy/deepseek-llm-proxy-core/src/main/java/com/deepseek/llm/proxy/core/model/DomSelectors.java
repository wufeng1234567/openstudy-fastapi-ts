package com.deepseek.llm.proxy.core.model;

import java.util.Map;

/**
 * DOM 选择器配置（BrowserExtensionProvider.getDomSelectors 返回）
 * <p>用于网页注入与控制，不同 Provider 选择器不同。</p>
 */
public class DomSelectors {

    /** 输入框选择器 */
    private String input;
    /** 发送按钮选择器（可选） */
    private String sendButton;
    /** 深度思考开关选择器 */
    private String deepThinkToggle;
    /** 对话模式选择器 */
    private String modeRadio;
    /** 文件上传 input 选择器 */
    private String fileInput;
    /** 关闭对话框选择器（可选） */
    private String dismissDialog;
    /** 额外选择器 */
    private Map<String, String> extraSelectors;

    public String getInput() { return input; }
    public void setInput(String input) { this.input = input; }
    public String getSendButton() { return sendButton; }
    public void setSendButton(String sendButton) { this.sendButton = sendButton; }
    public String getDeepThinkToggle() { return deepThinkToggle; }
    public void setDeepThinkToggle(String deepThinkToggle) { this.deepThinkToggle = deepThinkToggle; }
    public String getModeRadio() { return modeRadio; }
    public void setModeRadio(String modeRadio) { this.modeRadio = modeRadio; }
    public String getFileInput() { return fileInput; }
    public void setFileInput(String fileInput) { this.fileInput = fileInput; }
    public String getDismissDialog() { return dismissDialog; }
    public void setDismissDialog(String dismissDialog) { this.dismissDialog = dismissDialog; }
    public Map<String, String> getExtraSelectors() { return extraSelectors; }
    public void setExtraSelectors(Map<String, String> extraSelectors) { this.extraSelectors = extraSelectors; }
}
