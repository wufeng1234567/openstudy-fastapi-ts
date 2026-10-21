---
name: CodeArts 模型配置存储位置
description: CodeArts 的模型配置（如模型名 GLM-5.2）内嵌在二进制中，而非本地 SQLite 数据库
type: reference
from: Agent
---

CodeArts 的模型配置（包括模型名 `GLM-5.2`）内嵌在 `installers/bin/codearts.exe` 二进制文件中，而非存储在本地 SQLite 数据库里。

本地 `opencode.db` 中的 `account`、`account_state`、`control_account`、`preference` 表均为空，不包含模型配置数据。模型配置可能是服务端下发或编译时内置于二进制中。

**How to apply:** 未来调查 CodeArts 模型配置、模型切换或相关配置问题时，直接检查二进制文件而非本地数据库。
