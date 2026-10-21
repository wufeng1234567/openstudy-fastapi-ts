---
name: P11d 只扫注册表输出，不扫运行时系统提示词
description: _toolpref_probe P11d 的扫描范围是 registry.definitions()/describe()，不含运行期拼装的 system_prompt
type: feedback
from: Agent
---

**`_toolpref_probe` 的 P11d 只扫注册表输出（`registry.definitions()` 字符串 + `registry.describe()`），不扫运行时逐轮拼装的 system prompt（如 `build_agent_system_prompt` 的输出）。**

**Why:** 2026-10-09 阶段 2 设计用户智能体时，需要判断"用户自定义中文人设注入 system_prompt 会不会触发 P11d 判红"。核实探针实现：P11d 在 `_toolpref_probe` 里取 `_leaf_strings(registry.definitions())` + `_cjk_runs(registry.describe())` 两部分，**不含**运行期 system prompt。故用户中文人设进系统提示词**不会**触发 P11d——它扫的是注册表的静态描述，不是每轮提示词。

**How to apply:** 判断某处新增中文是否会踩 P11d 时，先确认该中文最终是否出现在 `registry.definitions()`/`registry.describe()` 的**静态输出**中；仅出现在运行期 system prompt（如用户人设、角色 prompt_fragment）里的中文不在扫描范围内。注意：`agent/roles.py` 的 `prompt_fragment` 进系统提示词同样不直接受 P11d 制约，但仍按既有"两轨语言约定"写英文（见 feedback-probe-model-side-chinese-whitelist）以保持惯例与防御一致性。

**P11d 判红的实操判据补充（2026-10-11 实证）：** 系统提示词里出现单个汉字 `图` **不触发** P11d 判红——它属**既有基线**（源自 image marker 的说明文字），不是本轮新增中文；只要本轮改动是纯英文即可通过。即判定"本次是否新增中文"应比对基线，而非见到任意中文字符就报红。

**工具 `description` 的实操硬约束（2026-10-10 并行委派轮确认）：** 改工具 `description` 为英文时，**新增内容里绝不能含中文，也不能加 `(xx)` 形式的中文括注**——因为 `description` 进 `registry.describe()`，任何中文都会踩 P11d。中文界面文案应放 `description_zh`，不要混进 `description`。
