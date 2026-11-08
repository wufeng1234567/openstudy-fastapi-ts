package com.deepseek.llm.proxy.core.model;

import com.deepseek.llm.proxy.core.enums.Capability;
import com.deepseek.llm.proxy.core.enums.ProviderMode;
import java.util.List;
import java.util.Set;

/**
 * Provider 信息（listProviders 接口返回）
 */
public class ProviderInfo {

    private String id;
    private String displayName;
    private Set<Capability> capabilities;
    private List<ProviderMode> supportedModes;
    /** 是否在线 */
    private boolean online;
    /** 是否为浏览器扩展型 */
    private boolean browserExtension;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getDisplayName() { return displayName; }
    public void setDisplayName(String displayName) { this.displayName = displayName; }
    public Set<Capability> getCapabilities() { return capabilities; }
    public void setCapabilities(Set<Capability> capabilities) { this.capabilities = capabilities; }
    public List<ProviderMode> getSupportedModes() { return supportedModes; }
    public void setSupportedModes(List<ProviderMode> supportedModes) { this.supportedModes = supportedModes; }
    public boolean isOnline() { return online; }
    public void setOnline(boolean online) { this.online = online; }
    public boolean isBrowserExtension() { return browserExtension; }
    public void setBrowserExtension(boolean browserExtension) { this.browserExtension = browserExtension; }
}
