---
name: 探针/脚本须先注册全部 SQLAlchemy 模型
description: 直接 import app.models.agent_config 或 service 而不先加载全部模型时，SysUser 的 SysRole relationship 未注册会导致 Mapper 崩溃；探针须先 register_all_models() 或 import app.main
type: feedback
from: Agent
---

**规则：** 独立探针/脚本若直接 import 单个模型（如 `app.models.agent_config`）或经 service 触发 ORM，而未先加载全部模型，会因 relationship 目标类未注册而崩溃。探针开头必须调用 `register_all_models()`，或 import `app.main`（它会触发全部模型加载）。

**Why:** 2026-10-09 跑阶段2用户智能体探针时无 stdout、疑似被 buffering 吞输出，实为直接 import 时 `SysUser` 的 relationship `SysRole` 未注册，mapper 配置报错。`agent_config_service` 只 import `app.database` + `app.models.agent_config`，不足以触发 `SysUser`/`SysRole` 解析。既有的 `_toolpref_probe` 之所以正常，是因为它 import 了 `app.main` 触发了全部加载。

**How to apply:** 写任何触及 ORM 的独立脚本/探针时，开头加 `register_all_models()`（或等效 import `app.main`）；排查"探针无输出"时优先怀疑模型未全加载导致的 import-time 异常，而非 buffering。
