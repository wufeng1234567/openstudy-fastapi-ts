package com.deepseek.llm.proxy.core.model;

import java.util.Objects;

/**
 * 图片数据
 * <p>支持 base64 data URL 形式传输，用于多图 OCR 和视觉理解。</p>
 */
public class ImageData {

    /** base64 data URL，如 "data:image/png;base64,iVBOR..." */
    private String dataUrl;
    /** 图片名称（可选） */
    private String name;
    /** MIME 类型，如 "image/png" / "image/jpeg" */
    private String mimeType;

    public ImageData() {
    }

    public ImageData(String dataUrl, String name, String mimeType) {
        this.dataUrl = dataUrl;
        this.name = name;
        this.mimeType = mimeType;
    }

    /** 快速构建：从 data URL 自动推断 mimeType */
    public static ImageData of(String dataUrl) {
        String mime = inferMime(dataUrl);
        return new ImageData(dataUrl, null, mime);
    }

    public static ImageData of(String dataUrl, String name) {
        String mime = inferMime(dataUrl);
        return new ImageData(dataUrl, name, mime);
    }

    private static String inferMime(String dataUrl) {
        if (dataUrl == null) {
            return "image/png";
        }
        int idx = dataUrl.indexOf(';');
        if (dataUrl.startsWith("data:") && idx > 5) {
            return dataUrl.substring(5, idx);
        }
        return "image/png";
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
        ImageData imageData = (ImageData) o;
        return Objects.equals(dataUrl, imageData.dataUrl)
                && Objects.equals(name, imageData.name)
                && Objects.equals(mimeType, imageData.mimeType);
    }

    @Override
    public int hashCode() {
        return Objects.hash(dataUrl, name, mimeType);
    }

    @Override
    public String toString() {
        return "ImageData{name='" + name + "', mimeType='" + mimeType + "'}";
    }
}
