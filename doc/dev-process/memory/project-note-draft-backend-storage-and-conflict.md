---
name: 智能体建草稿成了真实笔记——后端加"用户草稿"存储定案
description: 2026-10-11 定案——智能体 note_manage 建草稿会落成真实笔记；改为后端新增 user_note_draft 表（无 noteId）+ 前端写笔记页双源合并，覆盖前先确认；后端已实施中
type: project
from: Agent
---

2026-10-11 用户反馈 bug：**让智能体创建"草稿"，结果落成了真实笔记**（出现在笔记列表里，而非仅是编辑中的草稿）。

**根因**：智能体工具 `note_manage` 的 `create` 动作直接写 `note` 表，没有"草稿"这一存储语义——智能体侧无独立草稿落点，草稿概念只存在于前端 localStorage（`DRAFT_KEY='note_draft'`，见 project-note-draft-autosave-feature）。

**2026-10-11 定案方案（后端加"用户草稿"存储 + 前端写笔记页合并展示，覆盖前先提示确认）**：
- **后端**：
  1. 新增表 `user_note_draft`（**用户维度，一篇/用户**）：`user_id`(PK)、`title`、`markdown_content`、`category_id`、`tags`、`is_public`、`public_section_id`、`update_time`。
  2. 新增服务 `note_draft_service`（get/upsert/clear）。
  3. 新增工具动作 `note_manage` 的 **`save_draft`**（不复用 create 语义，语义更清晰）：写进 `user_note_draft` 而非 `note`；**若已有草稿 → 返回"已存在草稿，需确认覆盖"（走确认卡）**。
  4. API：`GET /notes/draft`（前端拉后端草稿）、`PUT /notes/draft`（前端保存/清除时同步）、`DELETE /notes/draft`。
- **前端**：「写笔记」页 `loadDraft` 由「后端草稿 + 本地 localStorage 草稿」**双源合并**（谁新用谁，或优先后端）；保存时**同时**写 localStorage 和（可选）后端。

**Why:** 用户明确「草稿不是正式笔记、没有 noteId」——**必须独立存储**，不能复用 `note` 表加"草稿标记"（Agent 已评估并否决该省事选项）。用户强调改动面大（新表+迁移+服务+API+工具+前端合并+冲突处理）须"仔细考虑"。

**How to apply:** 定案要求**先落设计文档**（用户授权文档直接产出落档；文档路径在 `docs/` 下，名 `fastapi_v2_智能体笔记草稿修正方案.md`），再分步实施：**先「后端表+服务+API+工具」→ 再「前端合并」**。加模型的落点=在 `register_all_models`（`openstudy-fastapi\app\database.py`，约 66-97 的模型列表）注册新模型，模型定义加在 `openstudy-fastapi\app\models\note.py` 末尾。最小可行范围=智能体 `save_draft` 写后端草稿表 + 前端读；前端本地草稿已有，只需再加"后端草稿"这一源并合并。

**2026-10-11 实施进展（后端阶段，分步「后端→前端」）：**
- **身份/出口修正**：实现走本地工作区 `openstudy-fastapi\`（**非** `openstudy-fastapi-ts\`）。
- **第 1 步已完成**：`UserNoteDraft` 模型加在 `app\models\note.py` 末尾；编译验证通过。**注册判定=无需手动另加**——`database.py` 已导入 `note` 模块，`UserNoteDraft` 同模块随 `note` 一并进 metadata 自动注册（`from app.models import note` 导入整个模块即注册 ✓）。
- **第 2 步已完成**：新增服务 `app\services\note_draft_service.py`（get/upsert/clear）；编译通过。
- **第 3 步进行中**：工具 `note_manage` 新增 `save_draft` 动作——**先看 `execute` 的动作分发处**再改。
- **How to apply:** 只改后端 3 处（model / service / tool 动作）+ API，前端合并留到后端收尾后再做；每步改完即编译验证。

**2026-10-11 第 3 步设计决策（`save_draft` 的确认机制拍板）：**
- **`save_draft` 放进 `_WRITE_ACTIONS`**（`app\services\ai\agent\tools\note_manage.py`），即**统一走工具级 `needs_confirmation` 确认卡**（调用前弹卡）。虽然用户原始要求是「**已有草稿时才提示确认**」，但仍选「每次写草稿都确认」——最简单、最一致（存草稿是写操作，弹卡让用户看到要存的标题/字数也合理）。
- **「已有草稿先提示」改用 preview 文案实现**：确认卡的 preview **区分「新建 vs 覆盖」**——已有草稿时 preview 明确写「你已有一篇草稿，确认将覆盖它」。
- **Why（为何不用动态确认）**：确认机制**只有工具级 `needs_confirmation`（调用前弹卡，返回 bool）**，**没有「回执内动态要求确认」的先例**；动态判断需看 DB（是否已有草稿），而调用前弹卡无法按 DB 内容决定 → 只能退化为「每次都确认 + preview 区分」。
- **本轮 4 处改动**：①工具 `enum` 加 `save_draft`（约 119-128）②工具 `description` 加 `save_draft` 说明 + **`status` 说明收窄**（约 89-106）③`execute` handlers 加 `save_draft` 分支 ④新增 `_save_draft` 方法 + `_preview_save_draft`，并 import `note_draft_service`（imports 约 1-40）。
- **How to apply:** 工具级确认卡是「调用前」机制，无法按 DB 状态动态决定是否弹卡；凡遇到「按数据状态才确认」的需求，一律用「统一确认 + preview 文案区分场景」实现。

**2026-10-11 第 3 步实施细节（`note_manage.py`，4 处改动的落点核对）：**
- **第 3 步实际落点（与上文预估行号不同，须按锚点读）：** `execute` handlers 的分发/错误文案区约 **369-388**；`_preview` 分发在约 **255-265**；`_preview_create` 在约 **308-332**（作为 `_preview_save_draft` 的写法参考）。
- **插入位置定案**：新增 `_save_draft` 方法插在 `_create` 结尾（`_update` 开始之前）；新增 `_preview_save_draft` 插在 `_preview_create` 之前，并在 `_preview` 分发加对应分支。
- **实操教训**：①一次 `edit` 时曾自疑「oldString/newString 重复了」，实际生成正确（`oldString` 与 `newString` 无误、无重复）；②按上文「约 119-128 / 89-106」的行号去改是**不可靠的**——必须以实时读到的区段为准，先读该区段再 edit。
- **How to apply:** 改 `note_manage.py` 这类长文件时，行号只当粗略定位，务必先读目标区段（execute 约 369-388、`_preview` 约 255-265、`_preview_create` 约 308-332）再按文本锚点 edit。

**2026-10-11 第 3 步收尾决策 + 第 4 步启动（undo 与 API 端点）：**
- **`save_draft` 保留在 `_WRITE_ACTIONS`（不参与 undo）**：曾评估「从 `_WRITE_ACTIONS` 移除 → 工具自返回需确认」的替代方案，被否决——因为那会退回「没有回执级确认机制」的老问题。最终**保留工具级确认卡**（每次弹、preview 指出 overwrite），`save_draft` 语义上本就临时、可再存，undo 意义不大。
- **`undo_plan` 须为 `save_draft` 特判**：原状是 `save_draft` 在 `_WRITE_ACTIONS` 里会被调 `undo_plan`，但它不建 note 行 → `_note_ids_of` 取不到 id → 返回 `undoable: False`，**reason 文案「定位不到行」有误导性**。改为**显式特判返回 `undoable: False` + 合理 reason**（如「草稿本身即临时内容，不支持撤销」）。改后已编译验证通过（`note_manage.py`）。
- **How to apply（undo 设计约束）**：`undo_plan` 的 `undoable` 判断依赖「能找到 note 行 id」；凡写操作不落 `note` 表（草稿类），都不能靠行定位，必须在 `undo_plan` 里显式特判并给用户可读 reason，禁止放它走到「定位不到行」这种误导性默认文案。
- **第 4 步（API 三端点）已启动**：在 `app\api\v1\notes.py` **文件末尾追加**三个草稿端点；该文件所在 router **无 prefix**，所有路径均写全（形如 `/notes/...`）。已先读文件 import 段与一个 GET 端点样例、再读文件末尾以定风格。**How to apply:** 给 `notes.py` 加端点时，路由路径写全（`/notes/draft` 等），并沿用该文件既有 GET 端点的返回风格。

**2026-10-11 第 4 步实施细节（三草稿端点已追加 + 编译通过 + 事务风格核查）：**
- **追加方式**：用 bash `cat >>` 向 `notes.py` 末尾追加三端点（`GET/PUT/DELETE /notes/draft`），追加后核查末尾中文**编码正常**（**本环境 bash heredoc/`>>` 默认以 UTF-8 写入**，未出现 GBK 乱码），随后编译 `notes.py` 通过。
- **事务风格发现（重要）**：本仓库 `get_db` 依赖**自动提交**——写操作无需手动 `await db.commit()`；因此在 `save_note_draft` 里手写的 `await db.commit()` 属**多余（虽无害但与既有风格不一致）**。
- **待确认点**：智能体工具路径（`note_manage` 工具）用的是 `ctx.db` 而非 `get_db` 依赖，其是否也自动提交**尚未核实**（正在查 `ToolContext.db` 来源）；若工具侧不自动提交，则工具里的写必须显式 commit。**How to apply: 给本项目新增写端点/工具时，先确认所选 session 来源（`get_db` vs `ctx.db`）是否自动提交，再决定要不要显式 `commit()`；`get_db` 侧一律不写 commit。**

**2026-10-11 第 4 步收尾（API 端点去掉显式 commit + 后端全部编译通过）：**
- **写工具不许自己 `commit`**：工具/服务侧的写操作**只能 `flush()`+`refresh()`**，**绝不 `commit()`**——因为会破坏上层（SAVEPOINT/事务）边界。已核对 `note_draft_service.upsert_draft/clear_draft` **只 `flush()`、没有 commit ✓ 正确**。
- **`get_db` 侧一致化（本轮实操）**：核对该文件其他写端点，**全部不显式 commit**（靠 `get_db` teardown 自动提交）。故**移除**新增两处 `await db.commit()`——显式 commit 后再 teardown commit 虽为 no-op（无害），但**消除风格分歧 + 避免双提交**。**How to apply:** 本仓 `get_db` 依赖的写端点一律**不写显式 `commit()`**，与文件内其他端点保持风格一致。
- **后端验证**：全部后端改动**编译通过**；随后验证 **`app.main` 可导入**（证明模型注册无冲突）。

**2026-10-11 第 5 步启动 + 草稿 API 路径统一（重要修正）：**
- **路径不一致发现**：既有笔记 API 路径都带 `/note/` 段（如 `/notes/note/list`），而第 4 步新加的草稿端点用的是 `/notes/draft`（**无 `/note/` 段**）。为与既有风格一致，**定案改为 `/notes/note/draft`**，并把后端三个草稿端点（`GET`/`PUT`/`DELETE`）路径**统一改到 `/notes/note/draft`**（3 处），改后 `notes.py` 编译通过。
- **`editor.vue` 文件亦须 `.vue` 语法校验**（本文件属 Vue 单文件组件，改动后须用 `_v.cjs` 单文件校验通过）。
- **第 5 步（前端合并）进行中**：`src/views/front/notes/editor.vue` 需 ①import 后端草稿 API（`getNoteDraft`/`saveNoteDraft`/`clearNoteDraft`）②`loadDraft` 合并后端+本地（谁新用谁）③`saveDraft` 同步后端 ④发布成功时清后端草稿。
- **前端 notes API 文件=`openstudy-vue3-ts\src\api\notes\note.ts`**（已有 `getNoteList` 等函数，路径形如 `/notes/note/...`）——**新增草稿 API 函数就加在此处**。
- **How to apply:** 给本仓笔记相关新增任何 API/端点时，**路径必须带 `/note/` 段**（`/notes/note/draft`），与既有 `/notes/note/list` 等保持一致，勿写成 `/notes/draft`。

**2026-10-11 第 5 步继续（`note.ts` 三草稿 API 已追加 + `editor.vue` 改造进行中）：**
- **前端 notes API 文件已落地**：`openstudy-vue3-ts\src\api\notes\note.ts` 末尾已追加三个草稿 API 函数（`getNoteDraft`/`saveNoteDraft`/`clearNoteDraft`），路径带 `/note/` 段。**实操方式=先 Read 该文件再 edit 追加**（比 bash 追加更稳）。
- **`editor.vue` 改造进行中**：①已改 import 段引入草稿 API；②下一步把 `loadDraft`/`saveDraft` 改为**异步 + 后端合并**（`loadDraft` 双源合并后端+本地、`saveDraft` 同步写后端、发布成功清后端草稿）。
- **How to apply:** 本轮与 `project-note-draft-autosave-feature` 是**同一功能的两层**——前者（localStorage 单草稿）已提交 `c079c82` 收口；本轮是**后端存储 + 前端双源合并**扩展，对应的 localStorage 侧改动见 project-note-draft-autosave-feature。改 `editor.vue`/`note.ts` 时先 Read 目标区段再按锚点 edit（长文件行号不可靠）。

**2026-10-11 第 5 步 async 化联动的关键点（幂等标记须在 await 前置位）：**
- `loadDraft` 改为 **async**（做后端双源合并）后，其调用方 `syncEditorMode` 也须改 **async** 并在内部 **`await loadDraft()`**；再往上的调用点（`onMounted` / `onActivated` / `watch`）须适配——`onMounted` 本身 async 可 `await`，`onActivated`（同步回调）与 `watch` 改用 **`void syncEditorMode()`**（显式不阻塞，避免 unhandled promise rejection）。
- **幂等标记 `newNoteDraftSettled = true` 必须在 `await loadDraft()` 之前置位**——因为 `await` 期间事件循环让出，`onActivated` 可能重入再次进入 `syncEditorMode`；若标记置在 await 之后，重入会在标记未置位时重复执行 `loadDraft`（弹两次提示回归）。同理 else 分支的 `loadDraft()` 调用也要 `await`。
- **How to apply:** 凡给"防重入"的幂等标记搭配 async/await 时，**先置标记再 await**，绝不能反序；调用点把同步回调包成 `void fn()` 以免 unhandled promise。

**2026-10-11 沙箱内验证进展（用户草稿表，探针 15/15 全绿）：**
- **`user_note_draft` 表已存在、0 行**（应用启动 `create_all` 已建过）。表由应用重启时的 `create_all` 建，沙箱内不重复建真实表（避免与应用 DDL 不一致）。
- **DDL 核对（同步，不需 DB）**：用 SQLAlchemy `CreateTable` 生成 DDL 字符串与手建表逐字段核对——**DDL 正确、字段齐备 ✓**；**须先 `register_all_models()`**（否则 `sys_user` 未注册会挂，见 feedback-probe-register-all-models）。
- **已知差异（无碍）**：手建表 `is_public INTEGER DEFAULT 1`（可空）vs 模型 `NOT NULL`（无 server default）——**应用层都赋值，不影响**。
- **临时脚本处置**：本轮验证用 `_ensure_draft_table.py`/`_gen_draft_ddl.py` 两个临时脚本**已删**；**保留 `tests\_probe_note_draft.py`（正式探针，入库）**；前端临时 `_v.cjs` 也已删。
- **How to apply:** 沙箱内验证"模型表能建 + 读写语义"时，`create_all` 需 async 跑不了；退化为 ①同步 psycopg2 手建表做读写、②`CreateTable` 生成 DDL 字符串做结构核对（先 register_all_models）；正式探针留在 `tests\_probe_note_draft.py`，临时核实脚本用完即删。

**2026-10-11 第 7 步（提示词引导）评估 → 跳过（不加系统提示词）：**
- **核对结果**：`prompts.py` 的 `AGENT_CORE_SECTIONS`/`AGENT_DOC_SECTIONS` 里**没有**笔记/草稿专门规则（笔记能力写在 `AGENT_DOC_BUILD_WORKFLOW` 之外，中文提示词也没提草稿）。
- **决策=跳过第 7 步、不加系统提示词**：工具 `description`（模型看 description 即知 `save_draft`）**已足够引导**模型——再加系统提示词属**冗余**且有 **P11d 风险**（新增模型侧中文）。
- **P11d 核对**：`save_draft` 的 `description` 是模型侧、**须无中文**；探针 ND-11 已通过 ✓。
- **How to apply:** 新工具的能力引导**优先靠工具 `description`**，不要顺手往系统提示词里加同义规则；若确需加，必须先确认不引入模型侧中文（P11d）。

**2026-10-11 提交完成（`c112d00` 已推 main）+ 后续发现"智能体仍走 create"未根除：**
- **本轮推送成功**：`ebd3429..c112d00 HEAD -> main`，worktree 已清理。提交范围=8 文件（5 改 + 3 新，含设计文档）；从 main 干净基线建 worktree **手工只落本轮改动**（`notes.py` +52、`editor.vue` +115/-45），无夹带。
- **须重启后端**：本轮新增 DB 表 `user_note_draft`，需重启让 `create_all` 建表（已验证表 DDL 正确、当前库中该表已存在）。

**2026-10-11 衍生 422 bug 已修复推送（草稿端点被动态路由抢先匹配）——`56af46e`：**
- **现象/根因**：`GET /notes/note/draft` 返回 **422**。根因=三个草稿端点原先**追加在 `notes.py` 文件末尾**，而**动态路由** `/notes/note/{note_id}`（GET）与 `/notes/note/{note_ids}`（DELETE）**注册在它之前**；FastAPI 按**注册顺序**匹配 → `/notes/note/draft` 被 `{note_id}` 抢先命中 → 把 `"draft"` 当 `int` 解析 → 422（`PUT` 因方法/路径组合不同未冲突）。
- **修法**：把草稿端点 `GET`/`PUT`/`DELETE /notes/note/draft` **整体前移**，插在 `/notes/note/public/{note_id}` 之前（即所有 `/notes/note/{...}` 动态路由之前）。
- **验证口径（重要）**：沙箱内不连库，改为**加载 `app.main` 实测路由表**——`/notes/note/draft` 注册序号 **186**、`/notes/note/{note_id}` = **191**、`/notes/note/{note_ids}` = **194**，**静态路由序号 < 动态路由序号 ✓**（修复前草稿排最后，必被抢占）。
- **提交**：worktree `.wt_route`，基线 tip=`0debb8e`，唯一改 `notes.py`，区间 `0debb8e..56af46e HEAD -> main`，推后已清 worktree。
- **How to apply:** 本仓 `notes.py` 给 `router` 加**字面量**端点时，必须**排在同前缀的动态端点之前**；FastAPI 匹配只看注册顺序、不按"更具体优先"。验证路由是否被抢占，最可靠的办法是 `import app.main` 后遍历 `app.routes` 看注册序号先后。

**2026-10-11 根治"智能体仍走 create"实施收尾（任务达终局）：**
- **旧路径已被彻底切断（成终局）**：`note_manage` 的 `create` 动作**删除 `status` 参数**、`_create` 内**硬编码 `status="published"`**（即智能体 `create` 只能建已发布真实笔记、不再能造草稿）；`_preview_create` 去掉 `status` 处理；`save_draft` 在 description/enum 里**前置**并加"说草稿必须用 save_draft、禁用 create"强制规则；`prompts.py` `AGENT_WORKFLOW_RULES` 加第 9 条草稿规则。**pivot：推翻此前"不加系统提示词、description 足够"的第 7 步决策**（已被证伪——模型没听 description）。
- **验证口径修正**：`tests\_probe_note_draft.py` 的 **ND-12 断言必须跟随实现改为"status 参数已删除"**（旧口径断言"status 说明指向 save_draft"必然判红）；**18/18 探针全绿**。
- **How to apply：** 智能体建草稿功能已闭环，后续如需再改工具入参形状，记得同步更新 `_probe_note_draft.py` 的 ND-11/ND-12 断言口径（勿为让探针变绿而回填已删的 `status`）。

**2026-10-11 重要坑：探针文件 `tests\_probe_note_draft.py` 在当前分支未被 git 跟踪（`git status` 显示 `??`）：**
- 现象：`git diff gitcode/main --stat` 把该探针显示为**整文件删除（-64）**，实为**未跟踪文件假象**；且 `git status` 实锤它是 `??`（未跟踪）——**并非被 `.gitignore` 忽略**（本仓明确禁止忽略 `_probe_*.py`，见 feedback-probe-gitignore）。
- 教训：**"未跟踪（`??`）"与"被忽略（`.gitignore`）"是两码事**，诊断时须分开查。`git diff` 对未跟踪文件会以"删除"形状呈现，切勿据此误判为文件被删/被忽略。
- **How to apply：** 提交前若某探针出现"-N 整文件删除"或 `??`，先确认它是否真的进了目标分支——**可能是此前提交漏了它**。定案=本轮提交前必须把 `_probe_note_draft.py` 显式 `git add` 入库。
- **用户复现回报（`c112d00` 后仍存在问题）**：原话「子代理创建笔记草稿的时候 还是直接创建的发表状态 依旧没有触发覆盖提示 继续创建一篇笔记草稿」。用户贴的日志回执=`笔记管理 · 创建`、状态 draft、笔记 ID=444、分类 ID 36 —— **这就是 `create` 路径，不是 `save_draft`**。
- **根因判断（关键）**：`save_draft` 虽已存在且 `description` 已写清，但**模型仍倾向选 `create`**——因为 `create` 在枚举/描述里**排第一**、且"创建一篇笔记"字面最贴；`create status=draft` 会建出**真实笔记行（进列表）**，与用户理解的"系统草稿"语义不符；没走 `save_draft` 自然也没有 overwrite preview。
- **根治方案（治"模型工具选择"，靠 description 不足以扭转）**：①**移除 `create` 的 `status` 参数**（从 parameters 删掉），`_create` 里 `status` **硬编码 `published`**——彻底断掉"create + status=draft 冒充草稿"这条歧义路径；②`_preview_create` 里的 status 处理一并移除；③`save_draft` 在 description/enum 中**前置** + 加**强制规则**（用户说"草稿/未完成/先存着" → **必须** `save_draft`，**禁止** `create`）。如此模型想"建草稿"时 `create` 无 `status` 可传 → 只能落到 `save_draft`。
- **Why:** 只加 `save_draft` 且写在 description 里**不足以改变模型的工具选择惯性**；必须让错误路径在参数层面**不可达**。
- **How to apply:** 当"加了新工具/新动作但模型仍走旧路径"时，不要只反复加强 description —— 要考虑用**移除旧路径的关键参数/入口**把误用路径物理切断；`note_manage.py` 的 `create/status` 即属此类（`note` 表的 draft 状态本就冗余，"草稿"语义唯一归 `save_draft`）。

**2026-10-11 提交阶段启动（本轮改动文件清单 + 前端耦合风险）：**
- **本轮改动文件**：后端 `models/note.py`、`services/note_draft_service.py`（新）、`tools/note_manage.py`、`api/v1/notes.py`；前端 `api/notes/note.ts`、`views/front/notes/editor.vue`；探针 `tests/_probe_note_draft.py`（新）；文档 `docs/fastapi_v2_智能体笔记草稿修正方案.md`。
- **fetch 得 main tip = `ebd3429`**（上一轮推送已更新，**非记忆里记的旧 tip——以实际 fetch 为准**）。
- **前端 2 文件疑与历史改动耦合**：`editor.vue` 相对 main 又是 `+348/-...` **放大差异**（同前几轮 `myNotes/index.vue`/`editor.vue` 老问题）；`note.ts` 相对 main `+28` 属正常。
- **`notes.py` 相对 main `+89`**——**已知文件内混有"收藏权限"历史改动**（上轮见过），故本轮的草稿端点（`GET/PUT/DELETE /notes/note/draft`）须与历史 hunk **隔离**搬运。
- **How to apply:** 后端 `notes.py` 不可整文件搬运（含历史 hunk），须隔离本轮草稿端点；前端 `editor.vue` 因放大差异同样不可整文件搬；提交走 worktree（见 feedback-git-worktree-isolation）。

**2026-10-11 提交阶段逐文件 hunk 归属核对（worktree 内实拍，隔离策略已验证）：**
- **一个文件里「本轮 hunk vs 历史 hunk」必须逐个 diff 块核对落点，不能按文件整体判**：`notes.py` 相对 main `+89` 里，**第 1351/1367/1410 号 hunk 是历史「收藏权限」改动，只有末尾 1492 号 hunk 是本轮草稿端点** → 只能隔离搬本轮那 1 块，绝不整文件拷贝（否则把历史收藏权限改动带进公开 main）。
- **纯本轮/纯新增文件可直接整文件拷**：`note_draft_service.py`（新文件）✓；`note.py`（相对 main **仅 1 个 hunk、末尾 `+29`**，纯本轮）✓；`note_manage.py`（相对 main **10 个 hunk 但全部对应本轮改动** import/`_WRITE_ACTIONS`/description/enum/status/undo/preview/execute/`_save_draft`，未混历史）✓。
- **前端 `note.ts` 已核对为纯本轮**：相对 main **`+28`**，纯属本轮 3 个草稿 API 函数新增，可整文件拷。
- **How to apply:** 判「能否整文件搬」的唯一可靠口径＝`git diff <main> -- <file>` 的**每一个 hunk 是否都落在本轮改动区域**；块少且在预期区域→整文件拷；出现历史块（如收藏权限）→只搬本轮 hunk。`note.py`/`note_draft_service.py`/`note_manage.py`/`note.ts` 已确认可整文件拷，`notes.py` 不可整文件拷。

**2026-10-11 提交阶段搬运策略落定（本轮 worktree 名 `.wt_nd`，按"纯本轮整拷 vs 耦合手工 edit"二分）：**
- **整文件拷（纯本轮/纯新增）**：`note.py`、`note_manage.py`、`note_draft_service.py`（新）、`note.ts`（+28 纯本轮）、探针 `_probe_note_draft.py`、设计文档。
- **worktree 内手工 `edit`（耦合历史 hunk）**：`notes.py`（**只加末尾草稿端点那 1 块**，用 `edit` 以末尾 `return success(sections)` 为锚点追加，不整文件拷）、`editor.vue`（只落本轮草稿改动）。
- **worktree 版 `notes.py` 末尾与工作区 main 版一致**（已实测）→ 可用同一 `return success(sections)` 锚点追加草稿端点。
- **worktree 目录名=`.wt_nd`**（位于项目根，如 `.wt_nd\openstudy-fastapi\app\api\v1\notes.py`）；本轮 worktree 从 main（含上轮 `ebd3429` 的草稿功能+幂等修复）检出，故 worktree 版 `editor.vue` **已含"同步版"的 `loadDraft`/`saveDraft`/`syncEditorMode`**，本轮须在其上叠加本轮改动（import 草稿 API、`loadDraft` async 双源合并、`saveDraft` 双写、`clearDraft` 清后端、`syncEditorMode` async+await、调用点 `void syncEditorMode()`）。
- **How to apply:** 本轮起 worktree 里 `editor.vue` 的基线不是"无草稿功能的 main 版"，而是"含上轮同步版草稿功能的 main 版"——改前先读 worktree 版 imports 与 draft 区，确认已存在哪些草稿函数，再叠加本轮（async 化/双写）改动，勿重复添加。

**2026-10-11 worktree `.wt_nd` 内 `editor.vue` 逐处 edit 已开跑（读 worktree 版 235-365 draft 全段 → 改 1~改 4 逐处落地）：**
- **先读 worktree 版 `editor.vue` 的 235-365 行（draft 全段）**，核对 worktree 版与工作区（改前）版**结构一致**后再动手落本轮改动。
- **改 1（import）已落地**：worktree 版 import 段引入后端草稿 API（`getNoteDraft`/`saveNoteDraft`/`clearNoteDraft`）。
- **改 2（`syncEditorMode` → async + `await loadDraft()` + 调用点适配）已落地**。
- **改 3（`loadDraft`/`saveDraft`/`clearDraft` 三函数改写：`loadDraft` async 双源合并、`saveDraft` 双写、`clearDraft` 清后端）已落地**。
- **改 4（调用点 `syncEditorMode` → `void`/`await`）进行中**（`onActivated`/`watch` 用 `void syncEditorMode()`、`onMounted` 可 `await`）。
- **How to apply:** worktree 内改 `editor.vue` 前**先读 worktree 版 draft 段（约 235-365）确认结构与工作区一致**，再按锚点逐处 edit；本轮 worktree 版基线已含上轮同步版草稿功能，故 import 段/`loadDraft`/`saveDraft` 已存在，本轮只做"async 化 + 双源/双写"叠加。

**2026-10-11 worktree `.wt_nd` 三处改动已落地 + diff 纯净性核对（提交前验证中）：**
- **`editor.vue` worktree 内改 1~4 已全部落地**（import 草稿 API / `syncEditorMode` async+await / `loadDraft`/`saveDraft`/`clearDraft` 三函数 / 调用点 `void`·`await`）。
- **diff 纯净性实测（worktree diff stat）**：`notes.py` **`+52`（仅末尾草稿端点 1 块，无历史"收藏权限"hunk ✓）**；`editor.vue` **`+115/-45`（相对脏工作区 `+348/-...` 大幅收敛，仅本轮 ✓）**；其余文件正常——**判定 worktree 内容干净**；随后核对 `editor.vue` diff 无杂质（逐块确认全部本轮）。
- **下一步=worktree 文件校验**：后端 worktree 编译（`py_compile`，worktree 内无 `.venv` 须用主工作区 venv 绝对路径、在对应目录下运行）+ 前端 `_v.cjs`（worktree 无 `node_modules`，须回主工作区跑、传 worktree 文件绝对路径）。
- **How to apply:** worktree 提交前判定"搬运是否干净"的实操口径＝`git diff --stat` 看放大差异是否收敛到本轮量级（`editor.vue` 收敛到 `+115/-45`、`notes.py` 只剩 `+52`），再逐块核对 diff 无历史 hunk；**校验顺序＝先 worktree 内后端编译（主 venv 绝对路径 + worktree cwd）→ 再回主工作区跑 `_v.cjs` 校验 worktree 的 `.vue`**。

**2026-10-11 提交推送完成（本轮闭环）：**
- **暂存 8 个文件已核对无误**：后端 `models/note.py`、`services/note_draft_service.py`(新)、`tools/note_manage.py`、`api/v1/notes.py`；前端 `api/notes/note.ts`、`views/front/notes/editor.vue`；探针 `tests/_probe_note_draft.py`(新)、设计文档 —— **提交说明文件 `_commit_nd.txt` 未暂存**（已知惯例）。
- **提交 hash = `c112d00`**；**推送前 fetch 确认远程 main tip 仍 = `ebd3429`（未变、无 non-ff），基线未滞后 → 直接推送成功**。
- **How to apply:** 本轮再次印证「提交前先 fetch 确认远程 tip 未变」的必要性（若已变则须删 worktree→fetch→重建）；提交说明文件（`_commit_*.txt`）与临时校验脚本一律不暂存、不入库。

**2026-10-11 `c112d00` 后的跟进（切断 create/status 路径 + 探针口径同步）：**
- **已编译通过**：本仓约定「改后必 `python -m py_compile`」——本轮 `note_manage.py` 移除 `create` 的 `status` 参数、`_create` 硬编码 `status="published"`、`_preview_create` 去掉 status 处理后编译通过 ✓。
- **下一步＝验证 P11d（description 无中文）＋跑探针**：先跑 `tests\_probe_note_draft.py`（含 ND-11 P11d）做验证。
- **探针 ND-12 口径同步（本轮实操）**：因 `status` 参数已删，ND-12 原断言「status 说明指向 save_draft」必红 → 改为「status 参数已删除」口径（改探针约 39-45 行区段）。
- **How to apply:** 与 `feedback-note-tool-cut-old-path-not-description` 配套——切断旧路径（删 `create.status`）属「实现侧」改动，**必须同时**同步 `_probe_note_draft.py` 的引用断言（ND-11/ND-12）并跑通 P11d 中文普查，二者是同一改动的两半，缺一即探针判红。

**2026-10-11 追加修复：推翻"不加系统提示词"的第 7 步决策，改在 `AGENT_WORKFLOW_RULES` 加第 9 条（英文）：**
- **决策反转（关键）**：此前第 7 步定的是「不加系统提示词、靠 description 足够」（见上文 84-88 行），**已被证伪**——模型没听 description、仍走 `create`。故**改为在 `prompts.py` 的 `AGENT_WORKFLOW_RULES`（英文编号列表）第 8 条之后追加第 9 条**，加一条"笔记草稿规则"（用户说草稿/未完成/先存着 → 必须用 `save_draft`、禁用 `create`）。
- **必须写英文**：系统提示词属模型侧，P11d 会扫；加规则只能用英文（P11d 风险），不得引入新增模型侧中文。
- **Why:** 仅靠工具 `description` 引导被证伪（模型工具选择惯性太强），需要模型侧提示词再加一层强引导；但语言必须英文以满足 P11d。
- **How to apply:** `prompts.py` 的 `AGENT_WORKFLOW_RULES` 是加"模型行为规则"的落点（已有第 8 条=碎片/歧义输入先澄清）；新增笔记草稿类规则追加为第 9 条（英文）。改后编译 + 走源码级/同步方式做 P11d 核对（见 feedback-import-prompts-side-effects-in-sandbox，裸 `import prompts` 在沙箱内跑不通）。

**2026-10-11 第二轮根治已推 main（`0debb8e`，区间 `c112d00..0debb8e`，worktree 已清理）：**
- **本轮根治四件套**：①`create` 移除 `status` 参数（`create` 一律硬编码 published，彻底断掉 `create + status=draft` 冒充"存草稿"）；②`_update` 同步移除 status 处理（改发布态交前端编辑器；**回退账本 `_NOTE_UNDO_FIELDS.status` 字段保留**）；③`save_draft` 提到 description/enum 最前并加重语气、`create` 明确写"建已发布笔记、**不要**用于草稿"（全英文，守 P11d）；④系统提示词 `AGENT_WORKFLOW_RULES` 第 9 条硬规则（英文）。
- **验证回执**：3 个文件编译通过；探针 `tests\_probe_note_draft.py` **18/18 全绿**（改 ND-12、新增 ND-16/ND-17/ND-18）；P11d 复检无新增中文。
- **⚠️ 遗留待用户决策（未处理）**：用户库里**已存在的 `status='draft'` 真实笔记**（ID 440/438/439/444 等）是此前误建产物——它们本就是**真实笔记（在列表里）**。本轮**未动**（删笔记属高风险操作，不擅自处理）。已向用户提出"是否要清掉这些误建 draft 笔记"（或用户自行在笔记页删）。**How to apply: 后续会话若用户提"草稿笔记""误建笔记"，指的是这批历史遗留行，删除须先取得用户明确许可。**
- **旧路径已彻底切断**：模型想建草稿时 `create` **已无 `status` 可传** → 只能走 `save_draft` → 写 `user_note_draft`（无 noteId、不进列表）；`save_draft` 走确认卡、preview 含 `overwrite`/`existingTitle`，已有草稿时明确提示将覆盖。

**2026-10-11 新 bug：笔记草稿端点被动态路由抢先匹配 → `GET/PUT/DELETE /notes/note/draft` 报 422：**
- **现象与根因**：`@router.get("/notes/note/{note_id}")`（`openstudy-fastapi\app\api\v1\notes.py` 约 573 行）**先于**文件末尾的草稿端点（约 1501 行）注册 → `/notes/note/draft` 被 `{note_id}` 匹配、`draft` 转 int 失败 → **422**。FastAPI/Starlette **按注册顺序匹配**，动态路径段会抢占字面量路径。
- **DELETE 同样中招**：`DELETE /notes/note/draft`（约 1537）落在 `DELETE /notes/note/{note_ids}`（约 761）之后 → `draft` 被当 `note_ids`。**PUT 不受影响**：`PUT /notes/note/draft`（约 1513）vs `PUT /notes/note`（约 674）路径不同（有/无 `draft` 段），无冲突。
- **修法**：把 `GET`/`PUT`/`DELETE` **三个草稿端点整体移到所有 `/notes/note/{...}` 动态路由之前**（落在 `GET /notes/note/public/{note_id}` 等第一条动态路由之前），即移除"字面量端点注册在动态端点之后"的隐患；先删末尾 3 端点整块、再插到约 518 行 `public/{note_id}` 之前。

**2026-10-11 路由前移的提交实施（worktree `.wt_route`，进行中）：**
- **fetch 得 main tip = `0debb8e`**（＝上一轮「笔记草稿工具选择」根治提交，即上一条 `.wt_nd2` 那轮的落点；**非记忆索引里记的旧 tip，以实际 fetch 为准**）。
- **本次 worktree 目录名 = `.wt_route`**（位于项目根）。worktree 版（基于 main=`0debb8e`）**已含草稿端点，但位置仍在文件末尾**（上一轮提交版）→ 即 worktree 版**自带 422 bug**，须在其上把端点**前移**。
- **改动面=仅 `notes.py` 一个文件**（把草稿端点从末尾移到动态路由之前），故不能整文件拷（工作区版 `notes.py` 还混有历史"收藏权限"hunk）→ **在 worktree 内手工 `edit`**：先删末尾草稿块、再插到 `public/{note_id}` 前（与工作区改法相同）。
- **worktree 版 `notes.py` 与工作区"改前"版一致**（已实测）→ 可用相同文本锚点做同样前移。
- **How to apply:** 本轮是「字面量端点被动态端点抢先匹配」的纯顺序修复，改动只在路由注册顺序；worktree 从含 bug 的 main 检出不代表无需改，须确认端点位置是否已在动态路由之前。
- **Why:** 字面量路径与动态路径混放时，**注册顺序即匹配优先级**——字面量端点必须排在动态端点之前，否则永远被动态路由吃掉。
- **How to apply:** 在本仓（无 router prefix、路径全写）给 `notes.py` 加任何 `/notes/note/<字面量>` 端点时，**一律放在 `/notes/note/{...}` 动态端点之前**；若已落在其后，用"整块删除 + 锚点前插"搬移，勿按行号搬。

**2026-10-11 路由顺序修复已实测验证通过：**
- **修复确认**：把三草稿端点前移后，用 FastAPI 路由表实测（列出含 `draft` 的路由顺序）——字面量 `draft`（注册序号 **#186**）**先于**动态 `{note_id}`（**#191**）与 `{note_ids}`（**#194**）✓，路由顺序正确，422 不会再发生。
- **口径提示：路由表序号与源码"约 518 行"是两套编号**，别混用；判断优先级看**注册序号**（`draft` 的序号必须小于 `{...}` 的序号）。
- **实现侧**：修复后 `note.py`/`notes.py` 编译通过；探路由顺序的临时脚本用完即删（见 feedback-temp-script-files-not-multiline:32）。
