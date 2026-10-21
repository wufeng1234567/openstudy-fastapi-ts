---
name: CodeArts CLI 底层是 opencode，留证数据位置
description: codearts CLI 底层为 opencode，会话/日志/差异原始数据存于 ~/.codeartsdoer/cli-data 下，非 session/export 子命令
type: reference
from: Agent
---

用户的 **codearts CLI 底层基于 opencode**。所有对话、操作、差异等原始留证数据都在 CLI 数据目录下（真实路径为 `<TOOLHOME>\`，**目录名 `.codeartsdoer` 带点**，注意第三方资料常误写成不带点的 `codeartsdoer`，实际不存在）。

真实留证数据位置（均在 `~/.codeartsdoer/cli-data/` 下）：
- `opencode.db`（SQLite，另带 `-wal`）—— 全部会话/提示词/回复，**完整对话记录在此数据库里**，这是最核心的原始证据。
- `log/*.log`（含 `experience-*.log`）—— 每次运行的完整操作日志。
- `storage/session_diff/` —— 每次代码改动的 diff。
- `tool-output/` —— 工具调用结果。
- `checkpoint/` —— 会话快照。

**注意**：外部流传的 `codearts session list` / `codearts export [sessionID]` 子命令可信度低，很可能并不存在；即便存在，最完整的对话原始证据仍在 `opencode.db` 中。要导出对话应读取 `opencode.db`。

**How to apply:** 需要为用户导出会话为可读 Markdown、采集"基于码道开发"证据时，直接以 `opencode.db` / `log/` / `storage/session_diff/` 为数据源，不要依赖未经验证的 `session`/`export` 子命令；用户已从 2026-10-08 起持续使用 CLI，真实记录已在库中自动沉淀。
