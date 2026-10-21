---
name: 子代理吐工具协议文本被当结论（已修复）
description: 知识库/题库"创建失败"真因=子代理把工具调用写成纯文本被当结论回报；修复+下拉整合+深度思考流式；提交 133e129 / ca1a1db
type: project
---

2026-10-10 用户报三个问题，均已修复并推送。

## ① 知识库/题库"创建失败"（真因：子代理吐工具协议文本被当结论）
**现象**：用户让智能体建知识库/题库，助手回"没建成"，聊天记录里子代理输出的是原始协议文本
（`＜｜｜DSML｜｜ invoke name="create_knowledge_base"＞` / `{"tool": ...}`）。
**真因**：子代理用的模型**没走 Function Calling、把工具调用写成了文本** → LangChain 的
`ai.tool_calls` 为空 → `_run_sub_agent_inner`（原第 174-177 行）**原样把 `ai.content` 当"子代理最终产出"**
返回 → 指挥家当 `delegate_task` 结果回报 → 工具**一次都没真正执行**（故"没建成"），用户看到乱码。
**修复（`app/services/ai/agent/sub_agent.py`）**：
- 新增 `_looks_like_tool_protocol(text)`：识别 DSML / `<invoke>` / `<parameter>` / 围栏 JSON /
  裸 `tool`+`action` JSON（口径对齐前端 `agentDsFree.ts#looksLikeToolCallAttempt`）。
  **`DSML` 作为强特征直接命中**（容忍全角/半角——用户记录里是全角 `＜｜｜DSML｜｜`；`DSML` 词本身在
  学习对话里几乎不出现，误伤风险极低）。
- `if not tool_calls:` 分支：命中协议特征 → **回灌纠正提示**要求改用真正 Function Calling
  （`SUB_AGENT_FORMAT_FIX_LIMIT=2`）；仍不改 → 返回 `success=False` + 明确错误，
  **绝不把协议文本当结论交回指挥家**。
- 探针 `_probe_parallel_delegate.py` 加 PD-09~12（识别 DSML/invoke/裸 JSON、正常文本不误伤）→ 12/12。

## ② 整合「智能体下拉框」（用户："明显多余"）
官方"专家"已由「专家」开关管理，下拉再列一遍官方角色与之重复。**修复（`chat.vue`）**：
设置面板下拉**移除「官方智能体」分组**，只留「自动」+「我的智能体」；该行 `v-if="myAgents.length"`；
标签改"我的智能体"，文案「自动（由主助手按需安排）」。`loadAgents` 只 `listAgentConfigs`（去掉
`listAgentRoles`）；删死变量 `agentRoles` 与 `listAgentRoles`/`AgentRoleMeta` import。
**命名统一**：用户可见层统一叫**专家**（开关/卡片），"我的智能体"专指用户自建角色。

## ③ 深度思考看不到流式输出（真因：前端折叠时机）
**后端链路完整**（已实测确认）：`loop.py` 第 1177-1182 行 `astream` 逐 chunk `_reasoning_of(chunk)`
发 `thinking`；`langchain_reasoning_patch` 补丁 **`INSTALLED=True`**（`langchain-openai 0.2.14`），
把 `reasoning_content` 注入 `additional_kwargs` —— 即 **api 链路本就能流式下发思考**。
**真因在前端 `AgentReasoning/index.vue`**：`scrollToBottom` 要求 `running` 才跟随、`watch(running)`
收口时**立即**折叠；而上游 reasoning 与正文/工具事件先后**无保证** —— `closeReasoning()` 可能因
"正文/工具卡先到"先收口（`secs` 有值），**但思考正文还在后续到达** → 块已折叠且不跟随 →
用户只能看开头，剩下要等全部结束才看得到。
**修复**：`scrollToBottom` 只看 `expanded`（不要求 `running`）；内容 watch 新内容到达时**取消挂起的折叠**
并保持展开；折叠改为**收口后延迟 1s**（窗口内来新内容则取消）；`onBeforeUnmount` 清 `collapseTimer`。

> **⚠️ 2026-10-11 改判**：本节③"真因在前端折叠"的结论**已被用户补充现象推翻**。用户实测为"深度思考**先喷几个字符→卡住→完毕才一次性全出**"，属**流式被攒批**（非折叠时序）；真凶=`main.py` 的三层 Starlette `BaseHTTPMiddleware` 缓冲 `StreamingResponse`，修复=改纯 ASGI 中间件。详见 `project-starlette-bashttpmiddleware-buffers-stream.md`。③ 的折叠改动（`ca1a1db`/`133e129`）仍保留但非根因。

## 提交
- `133e129`（区间 `eb841c4..133e129`）：协议文本兜底 + 下拉整合 + PD-09~12。全量 8 探针 EXIT=0 全绿。
- `ca1a1db`（区间 `133e129..ca1a1db`）：深度思考流式可见。

**Why:** 用户实测发现"创建失败"且聊天记录里出现 `<|DSML|>` 协议文本；下拉框与专家开关语义重复；
深度思考看不到流式。三者分别对应子代理协议兜底缺失、UI 重复入口、前端折叠时机 bug。
**How to apply:** ① 子代理/任何"模型产出当结论"的地方，都必须先检测协议文本（`_looks_like_tool_protocol`），
不能把原始调用文本当回答；② 用户可见的角色层统一叫"专家"，官方专家只由「专家」开关管、不再出现在
下拉里；③ 思考块的展开/折叠要容忍"收口后迟到增量"（别在收口瞬间折叠）。
