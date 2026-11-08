package com.deepseek.llm.proxy.core.model;

import java.util.Objects;

/**
 * 文件数据
 * <p>支持 base64 data URL 形式传输，用于 PDF/Word/TXT 等文档输入。</p>
 */
public class FileData {

    /** base64 data URL，如 "data:application/pdf;base64,..." */
    private String dataUrl;
    /** 文件名 */
    private String name;
    /** MIME 类型，如 "application/pdf" */
    private String mimeType;

    public FileData() {
    }

    public FileData(String dataUrl, String name, String mimeType) {
        this.dataUrl = dataUrl;
        this.name = name;
        this.mimeType = mimeType;
    }

    public static FileData of(String dataUrl, String name) {
        String mime = inferMime(dataUrl, name);
        return new FileData(dataUrl, name, mime);
    }

    private static String inferMime(String dataUrl, String name) {
        if (dataUrl == null) {
            return "application/octet-stream";
        }
        int idx = dataUrl.indexOf(';');
        if (dataUrl.startsWith("data:") && idx > 5) {
            return dataUrl.substring(5, idx);
        }
        // 按扩展名推断
        if (name != null) {
            String ext = name.substring(name.lastIndexOf('.') + 1).toLowerCase();
            switch (ext) {
                case "pdf": return "application/pdf";
                case "doc": case "docx": return "application/msword";
                case "txt": return "text/plain";
                case "md": return "text/markdown";
                case "csv": return "text/csv";
                default: return "application/octet-stream";
            }
        }
        return "application/octet-stream";
    }

    public String getDataUrl() { return dataUrl; }
    public void setDataUrl(String dataUrl) { this.dataUrl = dataUrl; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getMimeType() { return mimeType; }
    public void setMimeType(String mimeType) { this.mimeType = mimeType; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        FileData fileData = (FileData) o;
        return Objects.equals(dataUrl, fileData.dataUrl)
                && Objects.equals(name, fileData.name)
                && Objects.equals(mimeType, fileData.mimeType);
    }

    @Override
    public int hashCode() {
        return Objects.hash(dataUrl, name, mimeType);
    }

    @Override
    public String toString() {
        return "FileData{name='" + name + "', mimeType='" + mimeType + "'}";
    }
}
