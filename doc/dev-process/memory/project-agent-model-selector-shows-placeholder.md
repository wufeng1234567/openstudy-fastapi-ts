---
name: 智能体设置面板模型选择框显示「请选择」而非「自动」
description: 2026-10-10 用户报设置面板最上方模型框显示"请选择"；根因 AiModelSelector 空值语义 + restoreSelection 依赖 listAiConfig
type: project
from: Agent
---

2026-10-10 用户报第二个 bug：智能体页**设置面板最上方（设置 tab 顶部）的模型选择框显示「请选择」**，用户期望显示「自动」或默认模型名。

**相关事实**：
- `AiModelSelector` 被 **5 处**使用（analysis / chat / agent / ai-builder / question-builder），都依赖组件自身的 `restoreSelection()` 在 `onMounted` 时自动选默认。
- `restoreSelection()` 在 `fetchConfigs` 完成后调用；**若无历史记忆且列表里有 `deepseek-flash` 则 emit `deepseek-flash`**。若 `listAiConfig` 请求失败/返回空 → `allModels` 为空 → **不 emit** → 调用方 `model` 保持空串 → 组件显示 `placeholder`「请选择」。
- chat.vue 里 `model = ref('')`，空串语义 = **跟随后端默认模型**（并非错误）。

**定案修复方向（组件层，惠及全部 5 处）**：
1. 在 `AiModelSelector` 的 `el-select` 加一个 **「自动（跟随默认）」选项（value=''）**，并把 `placeholder` 从「选择模型」改为「自动」——空值不再显示"请选择"，且用户可主动选回"自动"。
2. chat.vue 的 `model` 初值**保持 `''`（= 自动）**，无需改。

**真因结论（2026-10-10 再研判）**：用户看到「请选择」= 组件层 `restoreSelection` **没生效**（`listAiConfig` 列表为空/请求失败 → 组件未成功 emit 模型 → 调用方 `model` 保持空串 → 落到空 placeholder）。正常情况下组件会自动选中 `deepseek-flash` 并 emit，应显示具体模型名。因此**根因是 `restoreSelection` 失败时无兜底**，而非 `model=''` 语义本身。本轮修复（组件层加「自动」选项 + placeholder="自动"）**正好充当兜底**：emit 成功 → 显示具体模型；失败 → 显示「自动」；**两种情况都不再是「请选择」**，符合用户预期。**保守取舍**：只做「请选择」→「自动」，**未**改 `restoreSelection`「无历史时自动选默认模型」的既有行为——因为其他 4 处调用（analysis/builder 等）依赖它保证总有一个具体模型；若用户还想要「默认就是自动」，那是行为变更，须另行确认（组件不知业务语义，不宜按场景分叉）。本轮只改 `AiModelSelector` 一个文件，`chat.vue` 与上轮 `8cd8391` 一致、无需再动。

**已落地并推送（2026-10-10，提交 `61af866`）**：推送区间 `8cd8391..61af866`（hook PASSED），最终版本选项 label 定为「自动（跟随默认）」、`value=""`，`placeholder` 从「选择模型」改为「自动（跟随默认）」，编辑 `AiModelSelector` 一处。效果：能拿到模型列表 → 自动选中 `deepseek-flash` 显示具体模型名；拿不到列表 → 显示「自动（跟随默认）」而非「请选择」。附带副作用（正向）：用户选过模型后**可切回自动**（此前切不回去）。验证方式：`@vue/compiler-sfc` + `typescript` 校验通过（本环境 esbuild 已禁用，见 feedback-frontend-vite-build-esbuild-flake）。本轮再次提示用户「`Hk41...` PAT 仍在用，建议到 `https://gitcode.com/setting/token-classic` 吊销重置」。
- **注意**：本条与 `8cd8391` 是**两个不同的提交**——`8cd8391` 修的是设置面板「工具清单一直加载 + 布局留白」（见 project-agent-settings-tool-load-failure），`61af866` 才是修「请选择」→「自动（跟随默认）」。

**Why:** `model=''` 本就表示"跟随后端默认"，UI 却把它渲染成"请选择"，语义误导用户；且这是组件级问题，只要 `listAiConfig` 慢/失败，5 个场景都会显示"请选择"。
**How to apply:** 后续涉及模型选择器的空值/占位显示，遵循"空值=自动（跟随默认）"语义；不要靠调用方设默认模型名去绕过，优先在组件层补「自动」选项与 placeholder。
