---
name: 扭转模型工具选择靠切断旧路径参数，而非只加强 description
description: 模型仍选旧工具（create）时，根治手段是移除旧路径的特有参数/硬编码为唯一合法值，而不是只堆 description 里的强制规则
type: feedback
from: Agent
---

**当模型固执地选择旧工具（而非新工具）时，根治手段是"切断旧路径"——移除旧工具的特有参数（或把参数硬编码为唯一合法值），而不只是在新工具的 `description` 里加"必须用 X、禁用 Y"的强制规则。**

**Why:** 2026-10-11 用户复现——子代理仍把笔记直接建成真实笔记、未触发覆盖提示，日志回执=`笔记管理·创建`（笔记 ID 444），即模型仍选 `create` 而非 `save_draft`。此前已在 `note_manage` 的 `save_draft` description/enum 前置并加强制规则，仍未扭转模型选择；最终定案=**移除 `create` 的 `status` 参数 + `_create` 硬编码 `status="published"` + `_preview_create` 去掉 status 处理**——让旧路径在参数层面不再表达"写草稿"的能力，模型自然失去走旧路的动机。

**How to apply:** 对付"模型不改用新工具"这类问题，优先改**工具的入参形状/语义**（删参数、硬编码、收紧 enum），把旧的错误路径从能力上关掉，而不是反复加长新工具的 `description` 或系统提示词规则；description 仅作辅助。改动涉及 `status` 时必须 `_create`/`_update`（及 `_preview_create`/`_preview_update`）成对核对，只改真正承载该语义的一侧。

**实施细化（2026-10-11 定案后的取舍链）：**
- **最终定案=`status` 参数彻底删除**（不再只是"改说明"），理由是"草稿"语义唯一归 `save_draft`，而笔记列表/前端编辑器本身已有发布态管理——故 `create`/`update` 都不再暴露 `status`，改状态走前端编辑器。
- **但 `_update` 里的 status 处理要保留**：`_update` 原本设置了 status（约 555-560）并在调用 `update_note` 时传入 `status=status_norm`（约 591）；schema 去掉 status 后 `params.get("status")` 永远取不到，故须**同步删掉 `_update` 的 status 设置与传参**（否则是死代码），并把相关错误文案一并改掉。
- **唯一例外：`_NOTE_UNDO_FIELDS` 里的 `status` 不要动**——那是撤销/回退字段，与工具入参无关，删了会破坏回退。
- **`is_public` 不要删**：它还承担"判断本次没有任何可更新字段"的用途，保留。
- 改动后必须**编译验证**（`python -m py_compile`）。

**连带改动（2026-10-11 实施回执）：** 删 `create` 的 `status` 参数时，同步把 `_create` 硬编码 `status="published"`、`_preview_create` 去掉 status 处理，`note_manage.py` 已 `py_compile` 通过；**但删参数会让引用它的探针断言失效**——`tests\_probe_note_draft.py` 的 ND-12 原断言「status 说明指向 save_draft」须改为「status 参数已删除」，同步后重跑 `_probe_note_draft.py` 验证 P11d（description 无中文）。**How to apply: 删参数/硬编码后，务必连带更新引用该参数的探针断言，探针口径跟随实现变化。**

**补强（2026-10-11 后续）：切断旧路径后仍不够时，可再加一层模型侧英文系统提示词规则。** 用户复现显示仅删 `create.status` + 加强 description 仍未完全扭转（模型仍可能选 `create`），故在 `prompts.py` 的 `AGENT_WORKFLOW_RULES` 第 8 条后追加**第 9 条英文「笔记草稿规则」**（说草稿→必须 `save_draft`、禁用 `create`）。**此前"只靠 description 足够、不加系统提示词"的判断已被证伪。** **How to apply:** 系统提示词规则**必须写英文**（P11d 扫模型侧中文）；`AGENT_WORKFLOW_RULES` 是加模型行为规则的既定落点；改后走源码级/同步方式做 P11d 核对（沙箱内裸 `import prompts` 跑不通）。

**2026-10-11 终局确认（第二轮修复已推 `0debb8e`，区间 `c112d00..0debb8e`）：** 仅删 `create.status` + 加强 description 实测**仍不够**，故本轮再加 `AGENT_WORKFLOW_RULES` 第 9 条英文硬规则；最终验证 3 文件编译通过、`tests\_probe_note_draft.py` **18/18 全绿**（ND-12 改口径、新增 ND-16/17/18）、P11d 无新增中文。**结论=「切断旧路径参数」是主手段 +「英文系统提示词规则」是必要补强，两者缺一模型都可能仍走旧路。** 另：用户库中此前误建的 `status='draft'` 真实笔记（440/438/439/444 等）未清理（高风险，待用户许可）。

**元教训（本条已犯两次，务必自查）：** 用 edit 做"新旧内容互换式"改写（把某段注释/代码换成另一段）时极易把 `oldString`/`newString` 顺序写反，造成内容重复；改完**立刻回读该处**确认无重复，再继续下一步。本次编辑时曾误判"改错了"，回读核实后其实正确——反之亦然，故回读是唯一可信的判定手段。
