---
name: 用户本地模型网关 magpie
description: 用户在本地运行统一网关 magpie (127.0.0.1:3425)，通过 OpenAI 兼容接口接入 DeepSeek 模型
type: user
from: Agent
---

用户在本地部署了一个统一模型网关，名称为 **magpie**，地址为 `http://127.0.0.1:3425/v1`，提供 OpenAI 兼容的 Chat Completions 接口。用户通过该网关使用模型 `group/auto-deepseek-v4-1-flash`（Auto DeepSeek V4 Flash）。

在 CodeArts CLI 配置中，provider ID 为 `magpie`，apiKey 为 `magpie`，模型 ID 严格为 `group/auto-deepseek-v4-1-flash`。

**How to apply:** 当用户提到模型配置、本地网关、DeepSeek 或 magpie 时，直接引用上述信息，无需重新询问网关地址或模型 ID。若用户遇到模型调用问题，优先排查本地网关 (127.0.0.1:3425) 是否正常运行。

**2026-10-12 用户报 bug 时再次给出同一套凭据（逐字）：「我的openstudy系统 连接magpie的本地统一网关 没法实现深度思考…本地地址 http://127.0.0.1:3425/v1 密钥magpie 模型group/auto-deepseek-v4-1-flash」** —— 即 **OpenStudy 应用侧也接的是这个 magpie 网关**（除 CodeArts CLI 的 provider 外），是用同样的地址/key/model。**当用户报"深度思考失效/不 work"时，除了应用代码，须把"magpie 网关是否透传 DeepSeek 的 `reasoning_content`"列为第一嫌疑**（网关若不返回该字段，应用侧无论怎么改都展示不出深度思考）。

**2026-10-12 关键实测铁证（根因锁定在网关侧）：** 网关共 **16 个模型**（含 `workbuddy/deepseek-v4-pro` 等）。对**同一模型 `group/auto-deepseek-v4-1-flash`** 实测：

| 请求体 | `reasoning_content` |
|---|---|
| 不带 `reasoning_effort` | **0 次**（74 个 chunk 全无）❌ |
| 带 `reasoning_effort: "high"` | **262 个 chunk 有** ✅ |

**结论：magpie 网关只有当请求体显式带 `reasoning_effort`（或类似开思考参数）时才返回 `reasoning_content`，否则一律不返回。** 这是"没法实现深度思考"的**根因不在 OpenStudy 应用**（后端有 `extra_body` 透传逻辑，见 memory 中 `db_config._thinking_extra_body`）。

**How to apply：** 排查深度思考问题，**先实测网关**（httpx/脚本发 `stream:true` 打 `/chat/completions`，对比带/不带 `reasoning_effort` 时 delta 是否含 `reasoning_content`）；确认网关开思考所需的参数名后，再核 OpenStudy 后端构造 LLM 时是否把该参数透传上游（及触发条件，如 `thinking_mode=auto` 时是否真构造 `extra_body`）。**勿跳过网关实测直接改应用代码。**

**2026-10-12 修复复测通过（口径）**：OpenStudy 用户实际链路最终跑通——**config_id=12 的 provider 原值实为 `deepseek`（非 `openai`，此前查库口径有误）**，其模型 `group/auto-deepseek-v4-1-flash` 实际由 magpie 网关承载；复测得 `extra_body={'reasoning_effort':'high'}`（干净、无 DeepSeek 脏参数）+ reasoning 分片 **112 个** ✅。**思考参数取舍的最终判据 = `api_base` 是否官方（`api.deepseek.com`）**：官方才发 DeepSeek 专有 `thinking:{type:enabled}`；非官方（含 magpie 网关）只发 OpenAI 标准 `reasoning_effort`（避免脏参数）。官方 deepseek 分支行为不变已验证。**故"按 provider 名判 deepseek"是错误口径，须按 base_url 判。**

**2026-10-12 修复经用户实机确认成功（用户原话「有深度思考了」）**：即"没法实现深度思考"经 `8e09bdf`（判据改为按 `api_base` 是否官方）修复后，用户实机**确认 magpie 链路能出深度思考** ✅。**故"OpenStudy 接 magpie 出不了深度思考"这一 bug 已闭环，勿再当未决问题重查。** 用户随后把注意力转向"添加模型应分官方/中转站两个 tab"的产品需求（见 `project-add-model-two-tabs-official-vs-custom-relay`）——那属**服务商语义划分**，不是深度思考仍坏。

**2026-10-12 补充（与实测吻合）**：**`reasoning_effort` 是 OpenAI 标准参数**（magpie 认）；**`thinking:{type:enabled}` 是 DeepSeek 专有形状**（勿发给非 deepseek provider）。OpenStudy 后端 `build_agent_llm`（`app\services\ai\db_config.py`）此前用 `is_deepseek = provider.startswith("deepseek")` 决定是否发思考参数，导致用户 `provider="openai"` 走 magpie 时**什么都不发** → 网关不返回 `reasoning_content`。修法=放宽为"非 deepseek provider 也发 `reasoning_effort`（不发 `thinking` 形状）"。
