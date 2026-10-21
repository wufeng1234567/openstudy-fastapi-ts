---
name: 沙箱内 import prompts 等重依赖模块易挂，源级/同步校验优先
description: 2026-10-11 沙箱内 import prompts 触发重依赖（疑似有 asyncio/DB/import 副作用）导致校验命令失败；验证 prompts.py 改动宜用源码级/同步校验，且 build_agent_system_prompt 需传参才能拼全提示词
type: feedback
from: Agent
---

**在本环境（CodeArts CLI / Sandbox）直接 `import prompts`（`agent/prompts.py`）跑校验常失败——该模块带重依赖/import 副作用，未必报出可读错误。验证其改动不要指望「裸 import 后调函数」，优先源码级断言或纯同步小探针。**

**Why:** 2026-10-11 编译通过 `prompts.py` 后校验 P11d（确认系统提示词无新增中文）时连续踩坑：
- 直接跑 P11d 检查脚本 → Error；查签名发现 `build_agent_system_prompt` 有 `include_tools` 参数；改为不传 tools，再跑仍 Error。
- 结论收敛：**失败更可能来自 `import prompts` 的重依赖/副作用，而非函数签名或参数**（"import prompts 可能有重依赖，查失败原因"）。
- 另确认函数语义：**`build_agent_system_prompt(include_tools=True)` 必须同时传 `tools_text`，否则 `{{TOOLS}}` 占位符不会被填充**（拼出的提示词缺工具段，校验会失真）。

**How to apply:**
- 要在本沙箱校验 `prompts.py`/系统提示词，优先：① 源码级/静态检查（grep 关键常量、分支、占位符）；② 纯同步小探针（不建事件循环、避免触发重 import 链）；避免直接 `import prompts` 走完整应用依赖。
- 调 `build_agent_system_prompt` 做端到端校验时，**务必同时传 `tools_text`**（`include_tools=True` 而是），否则 `{{TOOLS}}` 空、校验结论不可信。
- 与 `_toolpref_probe` 的 P11d 区分：P11d 只扫注册表静态输出，不扫运行期拼装的 system prompt（见 feedback-p11d-scans-registry-not-runtime-prompt），故「校验运行期提示词」须另用构建函数 + 源码级手段。
