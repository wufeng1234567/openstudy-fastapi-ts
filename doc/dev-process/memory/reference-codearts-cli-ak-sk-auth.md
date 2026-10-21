---
name: CodeArts CLI 子命令需要 AK/SK 环境变量认证
description: codearts models 等 CLI 子命令要求 CODEARTS_CLI_AK/CODEARTS_CLI_SK 环境变量，与 OAuth 登录是两套独立认证
type: reference
from: Agent
---

CodeArts CLI 的部分子命令（如 `codearts models`）要求设置环境变量 `CODEARTS_CLI_AK` / `CODEARTS_CLI_SK`（华为云统一身份认证的 AK/SK）才能运行，这与 OAuth 登录会话是**两套独立的认证机制**。未设置时会报错："认证失败，没有设置环境变量CODEARTS_CLI_AK/CODEARTS_CLI_SK"。

AK/SK 申请页面：https://codearts.huaweicloud.com/portal/settings/cli-auth

**关键区分：** 通过本地 magpie 网关路由的自定义模型配置（provider `magpie`）**不依赖**华为云 AK/SK 认证，也不消耗华为云积分/Token。只有 CLI 内置的华为云相关子命令才需要 AK/SK。

**How to apply:** 当用户运行 `codearts models` 或类似 CLI 子命令遇到认证失败错误时，直接说明这是 AK/SK 环境变量缺失问题，与自定义模型配置无关，无需排查模型配置文件。
