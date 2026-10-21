---
name: 流式卡顿真因——Vue 3 响应式陷阱（raw 引用）而非 Starlette 中间件
description: 2026-10-11 用户补充流式卡顿现象后定位几经翻转，终局定案=Vue 3 响应式操作了 raw 对象（此前误指向 Starlette BaseHTTPMiddleware）
type: project
from: Agent
---

## 2026-10-11 终局定案（覆盖此前 Starlette 判断）
「深度思考流式卡死/最后一次性全刷」的**真因 = Vue 3 响应式陷阱**：`useAgentChat.ts` 持有 **raw 对象引用**后直接改属性（如 `openReasoning.content += delta`）**不触发视图更新**；`appendText` 因从 ref 数组取出的是**代理**故正文正常，`appendReasoning` 用 **raw** 故推理卡死。修复 = 从 `messages.value` 取回代理再改。

## 2026-10-11 提交阶段实况（db_config.py 那一轮）
- 改完 `db_config.py` 后回归全绿；fetch 确认远程 main tip = `0a98e96`；`git diff` 显示 `db_config.py` **2 个 hunk，正对应两处改动**（无历史夹带）；走 worktree 提交，拷入 **3 文件 = `db_config.py` + 2 个探针**，随后查状态 + 编译。推送后的新 tip 以实际 fetch 为准。

## Why
用户多次复现"发出消息后卡住不动、结束才整批刷出"；前端曾两轮被误排除（只查累加/渲染逻辑、未查操作对象是 raw 还是代理）。
## How to apply
再遇此类卡死，**先判"改的是 raw 对象还是响应式代理"**，勿再从 `appendReasoning`/`AgentReasoning` 的累加/渲染逻辑入手；同类隐患含 `pendingPlaceholder`/`pendingProgress`/`openReasoning.secs` 等。
