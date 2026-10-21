---
name: 用户消息过短时复制按钮溢出气泡 + 浅显输入触发过度思考
description: 2026-10-11 用户报两 bug——用户气泡过短致复制按钮溢出（需 min-width/overflow 修）、输入"1"被 LLM 过度思考与乱调工具（须改提示词）
type: project
from: Agent
---

2026-10-11 用户报聊天界面两个"用户消息过短/浅显"相关 bug。

**✅ 已完成并推送（2026-10-11）：提交 `b96af7d`（区间 `9523688..b96af7d`）已推 gitcode/main，worktree 已清理。** 改动文件=`prompts.py`（Bug 2 的 `AGENT_WORKFLOW_RULES` 新增**第 8 条**先澄清规则）+ 前端 `AiChatStream/index.vue`（Bug 1 给 `.message.user .message-content` 加 `min-width: 96px`）。
- **Bug 2 规则内容（英文，守 P11d）**：输入是无法独立成立的碎片（孤立数字/单独的 "ok"/单词/`?`）且含义不确定时，**必须只回一句简短澄清问题、该轮不调任何工具**；不得猜测、不得随意选定解释、不得为猜意图跑一串工具。**仅当上一轮显式给出编号列表且映射唯一时，才可把 "1/2" 读作选项**。
- **校验口径**：`prompts.py` 编译通过 + P11d 核对（系统提示词中文段只剩既有的「图」，**无新增中文**）；`AiChatStream/index.vue` 经 `@vue/compiler-sfc` 校验通过。
- **遗留提醒（用户已知）**：本会话沙箱 asyncio 不可用，**未跑 async 端到端探针**；建议在正常环境补跑一次全量回归。

## Bug 1：用户消息气泡过短时复制按钮超出气泡框
- **现象**：用户输入极短内容（如 "1"）时，「复制」按钮跑到用户消息气泡框外。
- **定位**：落点 `openstudy-vue3-ts/src/components/AiChatStream/index.vue`；`.msg-copy-btn` 为 `position:absolute; right:12px; bottom:8px`，相对 `.message-content` 定位；用户气泡 `.message-content` 为 `max-width:75%` + 内容撑开（fit-content），内容极短时气泡宽度小于按钮宽度+内边距，absolute 按钮（无 `overflow:hidden`）即溢出到气泡外；用户消息行 `justify-content:flex-end`，气泡贴右。
- **修复方向**：给用户消息气泡一个 `min-width`（约 96px 量级，容得下复制按钮）并确保按钮落内；或按钮不参与布局但保证气泡最小宽度。

## Bug 2：输入 "1" 被 LLM 过度思考 + 自顾自乱调工具
- **现象**：用户只输入 "1"，模型深度思考一大段、擅自调用一堆工具，产出无意义回复。
- **根因**：上一轮助手末尾抛了两个选项（"…或…吗？"），用户回 "1"（歧义）；模型未先澄清意图，直接过度解读并自主行动。
- **修复方向（改提示词）**：在 `openstudy-fastapi/app/services/ai/prompts.py` 的 `AGENT_WORKFLOW_RULES` 增加"歧义/过短输入先简短澄清"规则——**输入含糊时先简短询问用户意图，不要擅自深挖与调用工具**。
- **P11d 风险（务必注意）**：该提示词规则**拟用英文示例**；Agent 一度在系统提示词里写了中文示例 `"你是想选第 1 项，还是有别的意思？"`，**这违反 P11d 白名单**（系统提示词不得新增中文，白名单仅 `{错题本, 斩题, 二次函数, 副本}`，见 feedback-probe-model-side-chinese-whitelist），须改为英文。

**Why:** 用户消息过短时的两个独立表现——① 纯前端样式缺陷（气泡最小宽度不足）；② 提示词缺陷（模型对歧义短输入缺乏"先澄清"约束）。二者都由"用户消息太短"触发，故一并记。
**How to apply:** 见 `AiChatStream/index.vue` 时先落实气泡 `min-width`；改 `AGENT_WORKFLOW_RULES` 时规则示例**只能用英文**，改完必跑 `tests/_toolpref_probe.py`（依赖 DB）确认 P11d 不判红。
