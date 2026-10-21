---
name: 自定义模型「一键获取服务商可用模型」需求与现状
description: 2026-10-12 用户要求给「添加自定义模型」加一键拉取服务商全部模型的功能；原理=OpenAI 兼容 GET /v1/models（当前项目与前端均未实现）
type: project
from: Agent
---

2026-10-12 用户报：在客户端（用户称「dsh 平台」）填好 API 地址（如 `https://api.siliconflow.cn/v1/`）+ API Key 后，点「获取可用模型」能直接列出服务商（如硅基流动 SiliconFlow）全部模型。原理=OpenAI 兼容规范的 `GET {baseUrl}/models` 端点：客户端把 baseUrl 拼上 `/models`、带 `Authorization: Bearer <API_KEY>` 发请求，服务端校验 Key 后返回该 Key 有权访问的模型 JSON 列表（`{"object":"list","data":[{"id":...,...}]}`），客户端解析并渲染 UI。因此 baseUrl 必须带 `/v1` 才能拼出正确的 `/v1/models`。

用户需求：给本项目的「添加自定义模型」也加上「一键获取服务商提供的模型」功能。

**Why:** 用户希望本平台自定义模型配置体验对齐该客户端，免手填模型名。

**How to apply:** 动工前的现状（供对照）——前端 `AiModelManager`（`openstudy-vue3-ts\src\components\AiModelManager\index.vue`）的「模型名称」实为**纯手动输入框**（约 70-75 行，`rules.model` 必填），**无「获取可用模型」按钮**；后端 `/models` 只列**已配置**模型，**无打上游 `{baseUrl}/v1/models` 拉取服务商模型的端点**。

**最新进度（2026-10-12）：已落地实现并编译通过。** 后端 `ai_config.py` 已改、`python -m py_compile` 通过；前端分两处：① `openstudy-vue3-ts\src\api\system\aiConfig.ts` 新增 `fetchProviderModels` API 函数；② `openstudy-vue3-ts\src\components\AiModelManager\index.vue`——补 import、在「模型名称」表单项旁加「获取可用模型」按钮、加选择弹窗及逻辑。

**已设计的实现方向（与用户描述原理一致）：**
1. 后端新增端点（拟 `POST /ai/models/fetch`），入参 `provider`/`baseUrl`/`apiKey`，**由服务端**请求 `GET {baseUrl}/models`（带 `Authorization: Bearer {apiKey}`），返回模型 `id` 列表——服务端代理可规避浏览器 CORS 并保护 Key 不落前端日志。
2. 前端在「模型名称」输入框旁加「获取可用模型」按钮 → 调该端点 → 弹选择/下拉，选中后填入 `form.model`。

**可复用资产（已核实）：** 后端已在用 `httpx`（可直接复用发上游请求）；已有「测试连接」端点 `POST /system/ai/config/test`（前端调 `testAiConnection`）——是现成的"服务端代打外部 AI API"写法参照，新端点应复用其模式。

**安全提示（须保留）：** API Key 会被发往 baseUrl 所属服务器，对接非官方「中转站」时存在 Key 泄露/滥用风险，实现时勿明文回显 Key。

**2026-10-12 关联需求（同一片 UI）：** 用户又定案把「添加模型」重做成**两个 tab**（我方预置各家官方 / 用户自己的中转站 api），用于从配置层区分服务商归属——见 `project-add-model-two-tabs-official-vs-custom-relay`。动「添加模型」UI 时，本"一键获取模型列表"与"官方/中转站分 tab"须一并考虑（官方 tab 可直接给预置 base_url，中转站 tab 才需手填 base_url + 拉列表）。注：用户把该客户端/平台称为**「dsh 平台」**。
