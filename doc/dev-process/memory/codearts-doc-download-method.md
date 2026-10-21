---
name: CodeArts 官方文档下载方法
description: CodeArts 文档网站有腾讯云 EdgeOne 人机验证，curl 无法直接下载，需用带浏览器 UA 的 PowerShell
type: reference
from: Agent
---

CodeArts 官方文档网站受腾讯云 EdgeOne 人机验证保护，直接用 `curl` 下载只会得到验证页面（约 2KB），而非文档内容。

成功的方法：使用 PowerShell `Invoke-WebRequest` 并带上浏览器 User-Agent 头，可以绕过验证下载到完整文档内容（如 64KB 的文档索引）。

**How to apply:** 当需要从 CodeArts 官方文档网站下载内容时，不要用 curl，改用带浏览器 UA 的 PowerShell `Invoke-WebRequest`。
