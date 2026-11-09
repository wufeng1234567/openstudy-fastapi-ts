# OpenStudy 代码质量审计与无用代码清理清单

> 文档版本：v2.0（2026-11-09 修订）
> 审计日期：2026-11-09
> 代码基线：`main @ 58f12c7`
> 范围：`openstudy-fastapi/`、`openstudy-vue3-ts/`、`.github/`、`doc/`、仓库根
> 口径：所有「确定」项都有文件/命令证据；「待确认」项写明风险，不直接建议删除。
> 本轮修订新增：悬浮助手残留死代码、智能图谱四套服务冗余、资料诊疗室 Agent 缺口、智能报告降级边界、笔记导入资料夹缺失、25 个 `.bak`、63 条既有未跟踪项（本目录文档资产另计）。
> 配套文档：`OpenStudy-系统完整介绍与功能架构梳理.md`（系统视角）、`LLM技术实现质量20%审查应对手册.md`（评审视角）。

---

## 0. P0 执行记录（2026-11-09 18:30）

本轮按本清单 P0 执行了第一批低风险、高杠杆项，全部改动均在本地，未提交 git：

| P0 项 | 状态 | 验收证据 |
|---|---|---|
| 统一版本号 | ✅ 完成 | `VERSION` 0.8.0、`openstudy-fastapi/pyproject.toml` 0.8.0；`package.json`/`main.py` 原为 0.8.0 |
| 修复 type-check 工具链 | ⚠️ 部分完成 | `vue-tsc` 不再因 TS 5.9 崩溃（锁 TypeScript 5.3.3、Node heap 8GB）；但首次运行暴露 **3,218 条存量类型错误**（strict 口径）；P1 第一批修 `request.ts` 返回类型与全局组件属性后降到 **1,980 条**，尚未达到 exit 0，列为 P1 首项 |
| pytest 配置 + 裸 pytest 可跑 | ✅ 完成 | 新增 `pytest.ini`（`testpaths=tests`、`asyncio_mode=auto`）与 `tests/conftest.py`；`pytest tests` → **100 passed, 9.12s**；6 个 script-style 文件（`test_agent_rag_tools.py`、`test_context_memory.py`）已加入 `collect_ignore`，仍可 `python tests/<file>.py` 运行 |
| ruff 配置 + 语法门禁 | ✅ 完成 | 新增 `ruff.toml`；`ruff check app --select E9,F63,F7,F82` → **All checks passed**；5 处裸 `except` 已改为 `except Exception` + loguru；4 个 F821 用 `TYPE_CHECKING` 修复 |
| ESLint/Prettier 基线 | ✅ 完成 | 新增 `eslint.config.js`、`.prettierrc.json`、`requirements-dev.txt`；`npm run lint` → **0 errors / 3,362 warnings**（存量债务以 warning 呈现） |
| 仓库卫生 | ✅ 完成（第一批） | 删除 `300`、`audit_ws_summary.json`、`type-errors.txt`、`ts_errors.txt`；删除 25 个 `.bak`；`.gitignore` 补 `_scratch*/`、`300`、`audit_ws_summary.json`、`doc/competition/码道架构图/` |
| 悬浮助手残留 | ✅ 完成 | 删除 `AiAssistant` 悬浮按钮拖拽逻辑（约 70 行）与 `.float-btn` 死样式（约 30 行）、`FrontSidebar` 死样式；全仓 `rg "float-btn"` → **0** |
| 死代码清理 | ✅ 完成（第一批） | 删除 17 个零引用 Vue 组件/页面 + 旧首页/dictation/chats + `utils/generator`（1,340 行）+ `PageWithFilter` + 后端 `favorites.py`/`notice_repo.py`/旧检查脚本；前端 `.vue` 从 276 降到 254，构建通过 |

**仍然未完成、留给 P1：**

1. **type-check 存量 1,980 条错误（初始 3,218）**：多数集中在 RuoYi 后台页（system/monitor/questionMarked/questionError 等）与历史组件；需要按文件批处理，先修 `request.ts` 返回类型、全局 `ComponentCustomProperties`、`ref({})` 泛型，再逐模块收紧。
2. **ESLint 3,362 条 warnings**：当前为 warn-only 基线，P1 按规则分组清理（`no-explicit-any`、`no-console`、`vue/require-valid-default-prop` 等）。
3. **CI 完整验证**：GitHub Actions runner 已实跑成功（run `42626308647`，3 jobs 全绿）；前置修复了干净 clone 的 uploadPath 建目录、pytest 的 PG env、空库 schema 初始化；type-check 作为报告型步骤保留，未清零。
4. **Git 提交**：本轮代码/文档已提交并推送；最新提交 `fb430ee`，工作区只剩用户文件 `智能体核心知识梳理.docx`、`智能整理测试集/` 未跟踪。

### 0.1 P1 第一批执行记录（2026-11-09）

| P1 项 | 状态 | 证据 |
|---|---|---|
| type-check 高杠杆收敛 | 🟡 进行中 | `src/utils/request.ts` 增加 `RequestInstance` 返回类型契约（响应拦截器实际返回 `res.data`）；`src/types/vue-globals.d.ts` 补 `$modal/download/parseTime/resetForm`；strict 错误 3,218 → **1,980** |
| Agent 工具中文标签 | ✅ 完成 | `AgentToolResult` 补 `document_compose/document_compare/english_practice/english_wordbook/micro_course_generate/review_sheet/chat_file_manage/mind_map/study_graph`；`AgentConfirmCard` 补 13 个缺失工具标签，覆盖 29/29 |
| 分页 helper | ✅ 完成（api/v1） | 新增 `app/utils/pagination.py`（`paginate` / `select_count`）；`api/v1` 的 `count_query = select(func.count())...` 模板已全部清零，`notes/questions/system/words/...` 均迁移 |
| ORM 分层 | ✅ 完成（4 个） | `Carousel` / `LeaveMessage` / `SensitiveWord` / `ChatMessage` 从 `api/v1` 迁入 `app/models/{carousel,leave_message,sensitive_word,chat_message}.py`，`database.register_all_models()` 统一注册 |
| 工具角色白名单 | ✅ 完成 5/7 | `document_compose`/`document_compare`/`chat_file_manage`→kb，`mind_map`→note，`review_sheet`→stats；仅 2 个英语工具仍只在 general |
| Agent 工具契约测试 | ✅ 新增 | `tests/test_agent_tool_contract.py` 校验 29 个工具的 name/description/parameters/label/description_zh、角色白名单引用和产物工具 `write_operation`；`pytest tests` 现为 **100 passed** |
| 写工具元数据 | ✅ 完成 | `document_compose` / `document_compare` / `micro_course_generate` / `review_sheet` / `study_plan` 已声明 `write_operation=True`（文件产物/快照，不强制确认） |
| P2 笔记导入工具 | ✅ 完成 | `note_kb_link` 表/服务/4 API + Agent 工具 + 笔记详情「加入资料夹」入口 |
| 调试残留清理 | ✅ 第一批 | `QuestionBuilder.vue` 25 处、`PracticeComponent.vue` 14 处、`CommentModal.vue` 15 处 `console.log` 已删除；全前端从 129～155 处降到 **56 处 / 14 文件** |
| 覆盖率基线 | ✅ 已建立 | `pytest tests --cov=app/services --cov-report=term-missing` → **19%**（20,620/25,327 行未覆盖）；CI 已加 `--cov` 仅报告、不设阈值 |

---

## 1. 结论与评分

**总评：中上水平的业务工程，但质量门禁基本没有接电；功能闭环有真实实现，但「无用代码」和「未清理的旧链路」仍然明显。**

| 维度 | 评分（本次审计） | 说明 |
|---|---:|---|
| 架构清晰度 | 6.5 / 10 | 目录分层清楚；P1 已迁出 4 个内联 ORM 模型，但 API 层仍有大量内联查询、图谱四套服务并存 |
| 代码可读性 | 6.5 / 10 | 注释/docstring 质量高；超大文件/超长函数拉低 |
| 可维护性 | 5.5 / 10 | 重复样板、死代码、双源依赖、双锁文件、旧链路未下线 |
| 测试资产 | 8.0 / 10 | P0 后 `pytest tests` 100 passed；已加 pytest.ini/conftest/CI step；仍无覆盖率门禁 |
| 工具链/门禁 | 6.0 / 10 | P0 已加 ruff/eslint/prettier/pytest + CI step；type-check 存量 1,980 错误仍未清零 |
| 仓库卫生 | 7.0 / 10 | P0 已删 300/audit/type-errors/ts_errors/25 个 `.bak`；既有历史未跟踪项仍在（见 P1） |
| 文档一致性 | 5.0 / 10 | 文档丰富；版本双轨、README 落后、子 README 仍是 Spring Boot |

**一句话：不是「烂尾仓库」，而是「有测试文化、有文档文化，但质量工具链没接电，旧版本的东西没清干净」。** 修 P0 约 1～2 天，就能把 LLM 评审眼中的「技术实现质量」从「工具链缺位」抬到「门禁齐全、有已知债务」。

### 1.1 与比赛评分「技术实现质量 20%」的对应

| 20% 子项 | 当前可得分 | 主要依据 | 最该补的证据 |
|---|---:|---|---|
| 工具使用是否规范（工程工具链） | 7 / 10 | P0 已加 ruff/eslint/prettier/pytest + CI step；type-check 存量 1,980 错误未清 | P1 类型批处理 + 清 warning |
| 工具使用是否规范（AI 编码工具留痕） | 8 / 10 | `doc/dev-process/` 日志/会话/memory/工具调用记录齐全 | README 质量节、证据索引 |
| 代码可读性与可维护性 | 7 / 10 | 注释、docstring、类型标注好；超大文件/死代码/重复样板 | 死代码清理 + P1 结构优化 |
| 综合（按 20 分折算） | **约 11～12 / 20** | 有测试/文档/架构，但门禁缺失、type-check 崩、死代码多 | 完成 P0 可到 15～16 / 20 |

---

## 2. 工程质量基线

> 以下为 `main @ 58f12c7` 审计时的原始基线；P0/P1 已执行的变更与当前结果见第 0 / 0.1 节。

### 2.1 后端

| 项 | 状态 | 证据 |
|---|---|---|
| 包管理 | ⚠️ `requirements.txt` 与 `pyproject.toml` 双源，版本已漂移 | `uvicorn==0.34.0` vs `^0.32.0`；`python-multipart==0.0.19` vs `^0.0.18` |
| pytest 配置 | ❌ 无 `pytest.ini` / `conftest.py` / `[tool.pytest]` | `git ls-files` 无相关文件 |
| pytest 依赖 | ⚠️ `pyproject` dev 组有 pytest/pytest-asyncio，但 `requirements.txt` 没有 | `pyproject.toml:55-58` |
| lint / format | ❌ 无 `ruff.toml` / `mypy` / `black` / `pre-commit` | 全仓无配置文件 |
| 一键检查 | ❌ 无 Makefile / justfile / 根脚本 | — |
| CI | ✅ `.github/workflows/ci.yml` 3 jobs（后端语法+导入、前端构建、仓库卫生） | `ci.yml:1-129` |
| CI 缺口 | ❌ 不跑 pytest、不跑 ruff | `ci.yml:54-73` 仅 `compileall` + import |
| 裸 pytest | 🔴 102 collected, 6 errors | `test_notice.py` + `_scratch/` 5 个临时测试 import 失败 |

### 2.2 前端

| 项 | 状态 | 证据 |
|---|---|---|
| scripts | ⚠️ 只有 dev/build/preview/type-check/check:dsfree；无 lint/format/test | `package.json:8-18` |
| type-check | 🟡 **P0 已修复工具链**：锁 `typescript@5.3.3` + Node heap 8GB，不再崩溃；P1 第一批后存量 1,980 条错误 | `npm run type-check` 可执行，当前仍 exit 2；错误清单见 P1 |
| tsconfig | ✅ `strict:true`、`noImplicitAny`、`strictNullChecks` | `tsconfig.json:6-8`；但缺 `noUnusedLocals/noUnusedParameters` |
| ESLint / Prettier | ❌ 无 | 全仓无配置 |
| 锁文件 | ⚠️ `package-lock.json` 与 `pnpm-lock.yaml` 并存；CI 用 `npm ci`，本地 node_modules 是 pnpm 布局 | 双锁文件 |
| 测试 | 自研 `check_agent_dsfree.mjs`、2 个 `*.test.mjs`；无 vitest/jest/Playwright | `openstudy-vue3-ts/tests/` |
| 构建 | ✅ `npm run build:prod` 实测 exit 0（3994 modules transformed） | 2026-11-09 本地 |

---

## 3. 无用代码清单

### 3.1 确定可删（P0，删除不影响行为）

> **执行状态：已在 2026-11-09 P0 批次删除。** 下表保留为清理依据与“删了什么”的评审台账；删除后 `npm run build:prod` exit 0。

| 对象 | 规模/证据 | 说明 |
|---|---|---|
| 根目录 `300` | 5 字节，内容仅 `966` | 命令行重定向手误产物 |
| 根目录 `audit_ws_summary.json` | 6.6 KB | 浏览器 console 抓取快照，一次性审计产物 |
| `openstudy-vue3-ts/type-errors.txt` | 43 行，npm EPERM 日志 | 被 git 跟踪的构建错误日志，评审一眼扣分 |
| `openstudy-vue3-ts/ts_errors.txt` | 空文件 | 被 git 跟踪的空错误日志 |
| `openstudy-vue3-ts/src/utils/generator/*` | 7 文件 1,340 行（`config.ts` 448 / `js.ts` 359 / `html.ts` 326 / `render.ts` 161 / 其他） | 全 `src` 搜索 `utils/generator` 0 引用；RuoYi 表单生成器脚手架残留 |
| `openstudy-vue3-ts/src/components/PageWithFilter/` | 0 引用 | RuoYi 脚手架残留；同类筛选已由 `CommonFilterSidebar` / `BankCardGrid` 模式替代 |
| `openstudy-vue3-ts/src/views/index.vue` | 200 行 | 旧轮播首页，未被 router 引用；文案还写「自习室预约 / 专注计时 / 成就激励」等未实现功能，且写「为在校学生打造」（应改「用户」或随页面删除） |
| `openstudy-vue3-ts/src/views/test/TestBank.vue` | 10 行 | 含 `console.log('测试组件加载成功')` 的调试页，无路由 |
| `openstudy-vue3-ts/src/views/dictation/dictation/index.vue` + `components/Dictation/DictationPractice.vue` | 约 1,919 + 全局注册组件 | 旧听写链路；C 端实际用 `english/listening`（3,166 行独立实现），`DictationPractice` 只在孤儿页使用 |
| `openstudy-vue3-ts/src/views/front/messages/chats.vue` | 1,342 行 | 路由组件已注释（`router/index.ts:361-366`），菜单 `v-if=false` |
| `openstudy-fastapi/test_notice.py` | 15 行 | 引用不存在的 `async_session`，裸 pytest 收集报错的直接原因之一 |
| `openstudy-fastapi/test_ds_free.py` | 旧 DeepSeek 网页反代验证脚本 | `doc/代码质量提升实施方案.md:51-52` 自标「陈旧脚本 / 手写验证脚本」；反代已废弃 |
| `openstudy-fastapi/app/api/v1/favorites.py` | 7 行空 router | 自述「收藏 API 已合并到 questions.py，此处保留空 router」；`main.py` 未导入 |
| `openstudy-fastapi/app/repositories/notice_repo.py` | 53 行，0 消费者 | 全仓 grep `notice_repo|NoticeRepository` 仅命中自身 |
| `openstudy-fastapi/check_images.py` | 旧 MySQL 检查脚本 | 含硬编码本地数据库口令、`aiomysql` 依赖；与当前 PG 架构不符 |
| `openstudy-fastapi/check_notice.py` | 旧公告检查脚本 | 与 `test_notice.py` 同批调试脚本，未见启动/文档引用 |

### 3.2 17 个零引用 Vue 组件/页面（P0 候选）

> **执行状态：已删除。** 删除前均经全仓 grep/import 检查，无任何 `.vue`/`.ts`/router 引用（除自身）；删除后 `.vue` 从 276 降到 254，`npm run build:prod` exit 0。

以下保留原始清单作为证据台账：

| # | 文件 | 物理行数 | 备注 |
|---:|---|---:|---|
| 1 | `src/views/front/workspace/components/KnowledgeMapPanel.vue` | 1,249 | 被 `KnowledgeWikiPanel` 内部图谱取代；后端 `/rag/knowledge-map` 只剩它在调 |
| 2 | `src/views/front/workspace/components/KnowledgeGraphSvgPanel.vue` | 710 | 旧实体图谱视图；后端 `/rag/knowledge-graph` 只剩它在调（实体图无活入口） |
| 3 | `src/views/front/workspace/components/StudyPlanDrawer.vue` | 249 | 旧计划抽屉，被 `KnowledgeAdviceHost` / `StudyPlanGenerativeCard` 取代 |
| 4 | `src/views/front/workspace/components/StudyPackPanel.vue` | 971 | 旧学习包面板；后端 REST 仍在，但前端 0 引用 |
| 5 | `src/views/front/workspace/components/StudyPackDialog.vue` | 806 | 同上 |
| 6 | `src/views/front/workspace/components/StudyPrescriptionPanel.vue` | 914 | 旧「学习处方」，本轮已改为「智能报告」；前端 0 引用；**内部仍有按天任务+勾选完成**，正是产品口径要淘汰的旧交互 |
| 7 | `src/views/front/workspace/components/DocumentHealthDialog.vue` | 774 | 被 `DocumentClinicDialog` 的 `DocumentHealthPanel` 取代 |
| 8 | `src/views/front/workspace/components/NodeAdvicePreview.vue` | 99 | 被 `NodeAdviceHistoryPreview` 取代 |
| 9 | `src/views/front/myQuestion/myStats/components/LearningLoopPanel.vue` | 837 | 旧学习闭环面板，学习统计页已移除 |
| 10 | `src/views/front/studio/components/BankInfoDialog.vue` | 302 | 旧题库信息弹窗 |
| 11 | `src/views/front/studio/components/CardOption.vue` | 113 | 旧卡片选项 |
| 12 | `src/views/front/studio/edit/index.vue` | 9 | 空壳/历史页，无路由 |
| 13 | `src/views/front/tools/text.vue` | 82 | 无路由；同目录其他工具页均有路由 |
| 14 | `src/views/front/courses/index.vue` | 103 | 无路由；`permission.ts:15` 仅有字符串残留 |
| 15 | `src/views/message/index.vue` | 200 | 后台留言页，无路由/无 import |
| 16 | `src/views/test/TestBank.vue` | 10 | 调试页 |
| 17 | `src/views/ai/test/index.vue` | 337 | AI 模型调试页，24 处 `console.log`；不在静态路由，需查 DB 菜单后再删 |

**另有页面级死代码：**

- `src/views/index.vue`（旧轮播首页，200 行）
- `src/views/dictation/dictation/index.vue`（1,919 行）+ `DictationPractice`（全局注册但只被孤儿页使用）
- `src/views/front/messages/chats.vue`（1,342 行）
- `src/components/DfSelfCheckPanel/index.vue`（581 行，0 引用；devtools store 仍被 `useAgentChat.ts:13` import，面板本身死）
- `src/api/english/index.ts`（1 行 barrel，无人引用）
- 25 个 `.bak` 文件（`useQuestionPractice.ts.bak-*`、`api/english/ocr.ts.bak-*`、`api/ocr/ocr.ts.bak-*`、`api/common/common.ts.bak-*`、`PracticeComponent.vue.bak-*`、`AnswerCard.vue.bak-*`、`TiptapEditor/index.vue.bak-upload-fix` 等；均未被 git 跟踪，属工作区垃圾）

### 3.3 「悬浮助手」残留死代码（本轮新增，P0 清理）

> **执行状态：已删除。** 全仓 `rg "float-btn"` → 0；`AiAssistant` 的 `initPosition` / `mousemove` / `mouseup` / `resize` 监听已移除。

当前产品**没有全局悬浮助手/悬浮球**：入口是侧边栏左上角品牌行的 `assistant-entry` 按钮（`FrontSidebar/index.vue:48-51`），点击派发 `openstudy:open-assistant`，由 `AiAssistant` 右侧抽屉承接（`AiAssistant/index.vue:3-9`、`1271-1273`）。但代码里残留约 100 行无用实现：

| 位置 | 内容 | 判定 |
|---|---|---|
| `AiAssistant/index.vue:511-580` | `isDragging` / `dragStart` / `btnPos` / `btnStyle` / `updateBtnStyle` / `initPosition` / `startDrag` / `onDrag` / `stopDrag` / `onFloatClick` 整套悬浮按钮拖拽逻辑 | 死代码；`initPosition()` 仍在 `onMounted` 调用、`mousemove/mouseup/resize` 仍绑定，但操作对象 `.float-btn` 在 template 中不存在 |
| `AiAssistant/index.vue:1379-1400` | `.assistant-entry` 样式（组件 template 中无该元素；真正活的 `.assistant-entry` 在 `FrontSidebar:839-857`） | 死样式 |
| `AiAssistant/index.vue:1402-1431` | `.float-btn { position: fixed; right:24px; bottom:32px; width:44px; height:44px; border-radius:50%; ... }` | 死样式，全项目仅此一处 `.float-btn` 字面 |
| `FrontSidebar/index.vue:859-868` | `.sb-assistant-slot` / `.sb-assistant-slot--collapsed` | 死样式，无模板引用 |
| `layout/front.vue:152-168` | 注释「全局悬浮 AI 助手」「不再叠一个悬浮球」「44×44 的实心主色浮球」 | 语义过时，应改成「全局 AI 助手抽屉（侧栏/事件唤起）」 |

**为什么必须清：** 用户已经明确「没有悬浮助手了，变成侧边栏左上角的 OpenStudy 助手，没有悬浮按钮了」。代码里保留 `position: fixed` 的 `.float-btn` 和拖拽监听，会让 LLM 评审/新同学误判系统仍有悬浮球，也让每次 `onMounted` 做无意义的坐标计算和事件绑定。

### 3.4 需确认后再删（P1）

| 对象 | 风险点 | 建议 |
|---|---|---|
| `views/courses/courses/index.vue` | 后台动态菜单可能按 `sys_menu.component` 挂载；该页仍假设「教师授课 + 学生选课」 | 查 `sys_menu` 后再删；若保留，产品口径需重定位 |
| `views/noteImage/noteImage/index.vue` | 前端有 API，但后端完全没有 `/noteImage` 路由 | 先确认是否死链；若确认，前后端一起删 |
| `views/ocr/ocr/index.vue` | 前台英语 OCR 用 `views/front/english/ocr`；后台旧 OCR 页无路由 | 查菜单后再删 |
| `views/ai/test/index.vue` | 可能是开发调试页，但后台菜单可能挂 | 查 `sys_menu`；若保留，至少移出生产构建 |
| `app/services/ai/deepseek_web_client.py` | 666 行旧 DeepSeek 网页反代；仅 `ai_config.py:489` 连通性测试引用，运行时不注册 | 确认无人使用后删除或移到 `legacy/`；同时清理 `pow_wasm/` |
| `StudyPrescriptionPanel.vue` / `StudyPackPanel.vue` / `StudyPackDialog.vue` | 前端 0 引用，但后端 `/rag/.../study-pack`、`/prescription` REST 仍在 | 如果产品确认旧「学习处方/学习包」入口已下线，前端组件与对应 REST 一起清理；否则补回页面入口 |

### 3.5 必须保留（不要误删）

| 对象 | 理由 |
|---|---|
| `tests/_probe_*.py` 等 59 个探针脚本 | `.gitignore:109-114` 明确注释为「刻意保留的零成本验证脚本，是仓库正式资产」 |
| `doc/dev-process/logs/*.log` | `.gitignore:49-51` 显式豁免，已脱敏，是开发过程证据 |
| 旧路由 redirect 群 | `bankCollect` / `questionCollect` / `wrongQuestion` / `masteredQuestion` / `myShares` / `myNotes` / `favoriteNote` / `weeklyReport` / `examPlan` 等是书签兼容，不是死代码 |
| `agentDsFree.ts` | 不是重复封装：后端 SSE 循环 vs 浏览器扩展前端循环，共享同一 AgentEvent 契约（`agentDsFree.ts:9-10`） |
| `learning_chart.py` | 辅助模块，不是「未注册工具」；`learning_stats.py:45` 引用它生成图表规格 |
| `micro_course_generate` 工具名 | 与 `roles.py:234` 匹配，名称正确 |
| `delegate_task` 永久排除 | 设计如此：防子代理递归委派，仅指挥家模式单独挂载 |
| `StudyAdvicePanel` 的「去练 N 题」 | 主题页详情的可选按钮，不是建议面板的强制跳转；不要误判成任务清单 |

---

## 4. 后端质量问题

### 4.1 Ruff 基线

本地 `ruff check app --statistics` 共 **6,473 条**（默认规则）。关键项：

| 规则 | 数量 | 含义 |
|---|---:|---|
| UP006 | 2,612 | 非 PEP 585 泛型（`List[...]` → `list[...]`），多为风格 |
| UP045 | 1,638 | `Optional[X]` → `X | None`，风格 |
| B008 | 1,001 | 函数默认值调用（FastAPI `Depends()` 是刻意模式，需 per-file ignore） |
| UP035 | 324 | 过时导入 |
| BLE001 | 192 | `except Exception` 宽捕获 |
| I001 | 151 | import 排序 |
| **F401** | **116** | **未使用导入（真问题，可清）** |
| **F841** | **8** | **未使用变量（真问题）** |
| **E722** | **5** | **裸 `except:`（真问题）** |
| **S110** | **36** | **try-except-pass（真问题）** |
| RUF012 | 42 | 可变类默认值 |
| F821 | 4 | 未定义名（模型 forward refs，需 TYPE_CHECKING） |

> 建议不要一次开全量规则；先落 `ruff.toml`，只开 `E9/F63/F7/F82`（语法/未定义名）和 F401/F841/E722，再逐步收紧。B008 必须 ignore，否则 FastAPI 项目会被 1,001 条噪音淹没。

### 4.2 超大文件 / 超长函数

**后端 Top 文件（物理行数）：**

| 行数 | 文件 |
|---:|---|
| 4,027 | `openstudy-fastapi/app/api/v1/questions.py` |
| 3,153 | `openstudy-fastapi/app/api/v1/rag.py` |
| 2,676 | `openstudy-fastapi/app/services/ai/agent/loop.py` |
| 2,460 | `openstudy-fastapi/app/services/rag/wiki_service.py` |
| 2,159 | `openstudy-fastapi/app/services/bank_export_service.py` |
| 2,150 | `openstudy-fastapi/app/services/rag/workspace_service.py` |
| 2,062 | `openstudy-fastapi/app/api/v1/ai.py` |
| 1,706 | `openstudy-fastapi/app/api/v1/notes.py` |

**函数 ≥120 行的有 53 个**；最长的：

| 函数 | 位置 | 行数跨度（含注释/空行） |
|---|---|---:|
| `run_agent_stream` | `agent/loop.py:1160` | 约 1,382 行（有效代码约 670 行） |
| `_run_sub_agent_inner` | `agent/sub_agent.py:226` | 376 |
| `build_study_map` | `rag/study_map_service.py:338` | 322 |
| `init_db` | `database.py:110` | 316 |
| `_convert_node` | `services/mathml_omml.py:218` | 305 |
| `plan_learning_route` | `rag/learning_route_service.py:332` | 279 |
| `build_wiki_pages` | `rag/wiki_service.py:805` | 276 |
| `build_weekly_report` | `learning_report_service.py:95` | 271 |
| `stream_turn` | `ai/chat_engine.py:511` | 266 |
| `build_study_plan` | `study_plan_service.py:523` | 234 |

### 4.3 分层违规（LLM 评审重点扣分项）

- `api/v1` 43 个文件中有 **250+ 处直接 `select(...)`**。
- **4 个 ORM 模型原定义在路由文件里，P1 已迁出**：
  - `app/models/carousel.py` `Carousel`
  - `app/models/chat_message.py` `ChatMessage`
  - `app/models/leave_message.py` `LeaveMessage`
  - `app/models/sensitive_word.py` `SensitiveWord`
- 规范做法：模型进 `app/models/`，路由只做参数校验/权限/响应；业务查询进 service 或 repository。
- `repositories/` 只有 4 个文件；`notice_repo.py` 无消费者。README 写「repositories # 数据访问」，实际大部分查询在 API/service。

### 4.4 异常处理

- **裸 `except:` 5 处**：`api/v1/auth.py:101`、`ai.py:405`、`notes.py:1103`、`notes.py:1138`、`notice_front.py:68`。
- `except Exception:` 57 处；大多有 loguru 日志，但存在静默吞掉模式（`monitor.py:48,111,227`、`micro_course_export_service.py` 7 处、`question_bank_link.py:41-43` 后台知识点抽取失败直接 `pass`）。
- **P0 修复建议**：5 处裸 except 改为 `except Exception as e:` + `logger.exception(...)`，每处附一句「为什么可降级」；不要一次性改 57 处宽异常，先清理裸 except 与 `pass`。

### 4.5 重复代码

- **分页样板重复 29 处**：原 `count_query = select(func.count()).select_from(query.subquery())` 分布在 `notes.py` 6 次、`questions.py` 5 次等；P1 已新增 `app/utils/pagination.py` 并完成 `api/v1` 清零（`repositories` 仅剩 3 处历史写法）。
- **Provider base_url 重复硬编码**：`db_config.py:33-37` 已有集中表，但 `siliconflow_client.py:78,150`、`deepseek_client.py:84,203,239` 各写一份。
- **分享模块对称复制**：`bankShare.py` 与 `kbShare.py` 结构几乎逐行对称。
- **Agent 双循环**：后端 `loop.py` 与前端 `agentDsFree.ts` 各自实现工具循环（设计使然，但缺常量一致性契约测试）。

### 4.6 图谱四套服务冗余（本轮新增，架构债）

| 服务 | 行数 | 端点 | 现状 |
|---|---:|---|---|
| `rag/knowledge_map_service.py` | 342 | `GET /rag/knowledge-map` | 旧页面层级图；唯一调用方是零引用组件 `KnowledgeMapPanel.vue` |
| `rag/knowledge_graph_service.py` | 955 | `GET /rag/knowledge-graph`、`POST /build`、`GET /entity/{id}` | 真实体图底座；上传后自动构建，供知识百科生成使用；实体图 UI 是零引用组件 `KnowledgeGraphSvgPanel.vue` |
| `rag/study_graph_service.py` | 686 | `GET /rag/study-graph` | 旧学习图；Agent `study_graph` 工具调用；前端主页面未直接使用 |
| `rag/study_map_service.py` | 662 | `GET /rag/study-map` | 六类统一图；`study_advice_service` 调用；前端只用于「按来源更新」下拉 |

**问题：**

1. 4 个服务各自定义节点 ID、边类型、空态口径，维护者与评审难以判断「哪个是权威图」。
2. `/rag/knowledge-map` 与 `/rag/knowledge-graph` 的前端调用方都是零引用组件，形成「有 API、无页面」的假功能。
3. `/rag/study-map` 的六类节点能力（document/web/note/image）没有真正作为主图谱展示，只在建议 trace 和来源选择里用到——`KnowledgeWikiPanel.vue:2008` 的画布用 `getWikiGraph`（page-only），`getStudyMap` 只在 `:1856` 用来列「可更新来源」。
4. **边 ID 已稳定（P2 修复）**：`study_map_service._add_edge` 已改为 `e:{kind}:{sha1(source->target)[:16]}`，同一 source/target/kind 的边 ID 可跨请求复现，不再依赖插入顺序；`tests/test_study_map_service.py` 已加回归断言。
5. **规模化硬墙**：`build_study_graph` / `get_wiki_graph` 页/链接查询无 LIMIT；`_has_pages` 为 O(来源×页)；无物化图快照。30 万页级不可行。
6. 建议收口为「一个统一图服务 + 一个页面图投影 + 一个实体图投影」，边 ID 改为 `(source,target,kind)` 内容派生，旧端点保留兼容层或明确标记 deprecated。

**这不是「无用代码」但属于「重复实现」，是 LLM 评审会指出的架构问题。**

### 4.7 Agent 工具元数据与能力缺口（本轮新增）

| 问题 | 证据 | 影响 |
|---|---|---|
| 29 个工具无资料体检/智能报告/整理/题库关联/笔记导入 | `tools/__init__.py:49-146` 全量注册表；grep 零命中 | 「一切皆对话」在资料域断链 |
| 4 个写工具无确认/回滚 | `study_plan`、`english_practice`、`micro_course_generate`、`review_sheet` | 写操作可能不可回退 |
| 工具角色白名单 | ✅ P1 已分配 5 个：`document_compose`/`document_compare`/`chat_file_manage`→kb，`mind_map`→note，`review_sheet`→stats；仅 `english_practice`/`english_wordbook` 仍只在 general | 英语专家模式仍可能找不到工具；其余已缓解 |
| 20/29 工具无 `jumpUrl` | `jumpUrl` 仅 8 个文件命中 | 工具结果最后一公里缺失 |
| 19/28 结果卡、15/28 确认卡有中文标签 | `AgentToolResult/index.vue:440-469`、`AgentConfirmCard/index.vue:255-273` | 英文内部标识符外露 |
| `learning_stats` 声明 `write_operation=True` 但只读；`bank_export` 声明 True 但确认恒 False | `learning_stats.py:150`、`bank_export.py:190/195-204` | 工具元数据口径漂移 |
| 资料体检/智能报告等新能力未挂角色 | `roles.py:239-260` kb 专家只「指路」 | 用户必须离开对话 |

### 4.8 后端正面信号

- 0 处 `print`，统一 loguru（60 个文件 import）。
- 0 处可变默认参数（ruff B006 无命中）。
- 0 个硬编码 `sk-` 类密钥（CI 也有密钥扫描）。
- `from __future__ import annotations` 与 `Mapped`/`mapped_column` 类型标注广泛使用。
- 模块 docstring 记录边界、踩坑、契约，质量远高于普通业务代码。

---

## 5. 前端质量问题

### 5.1 类型检查与构建

- **P0 已修复工具链**：`typescript` 锁 `5.3.3` + `node --max-old-space-size=8192 ./node_modules/vue-tsc/bin/vue-tsc.js --noEmit`，不再因 `vue-tsc@1.8.27` + TS 5.9.3 崩溃。
- **但首次运行暴露 3,218 条存量类型错误**：集中在 RuoYi 后台页（system/monitor/questionMarked/questionError）、历史组件与 `request.ts` 返回类型；已验证 `request.ts` 可先做统一返回类型收敛，P1 按文件批处理。
- `npm run build:prod` 实测 exit 0（vite build 不做类型检查，所以「能构建」不代表「类型正确」）。
- 仍需决定 `package-lock.json` vs `pnpm-lock.yaml` 唯一锁文件（当前 npm lock 被前端 .gitignore 忽略，CI 用 npm install 兜底，建议 P1 固化）。

### 5.2 类型/调试/巨型文件

| 指标 | 数值 | 重灾区 |
|---|---:|---|
| `: any` / `as any` | 约 1,379～1,958（不同统计口径） | `workspace/index.vue` 163；`KnowledgeWikiPanel.vue` 124；`PracticeComponent.vue` 78 |
| `console.log` | 约 129～155 | `QuestionBuilder.vue` 25+；`ai/test/index.vue` 24；`DictationPractice` 16；`chats.vue` 15 |
| `>1500 行 .vue` | 14 个 | `workspace/index.vue` 6,512；`QuestionBuilder.vue` 5,445；`PracticeComponent.vue` 3,797；`english/listening/index.vue` 3,166；`KnowledgeWikiPanel.vue` 2,856 |
| 内联 `style="` | 466 处 | 多个后台/前台页存在重复校验提示块 |

### 5.3 重复实现

- **OCR 双实现**：`components/OcrRecognizer/index.vue:460` 与 `views/front/english/ocr/index.vue:1166` 出现同一句 `console.log('流式结果不是标准 JSON，尝试文本解析')`，明显复制粘贴；应抽共用 composable/service。
- **上传/预览/抽屉变体**：`FileUpload`、`ImageUpload`、`ChatFileUploader`、`ChatFileAssetCard`、`OcrRecognizer`、`ImagePreview`、`DocxPreview`、`ResizableDrawer`、`KnowledgeBaseDrawer` 并存；部分全局注册（`main.ts:67-84`），部分局部使用，需按调用点合并。
- **双锁文件**：`package-lock.json` 与 `pnpm-lock.yaml` 同时存在；CI 用 npm，实际 node_modules 是 pnpm 布局，构建环境与本地可能不一致。

### 5.4 前端死代码

见 3.1/3.2/3.3；总计：

- 17 个零引用组件/页面（P0 已删除）；
- 旧首页 1 个、旧听写链路 2 个、私信 1 个、开发自检面板 1 个（P0 已删除）；
- `utils/generator` 7 文件 1,340 行（P0 已删除）；
- `AiAssistant` 悬浮按钮残留约 100 行 + `FrontSidebar` 死样式（P0 已删除）；
- 25 个 `.bak` 文件 + 构建日志 30+ 个（P0 已删除 `.bak`）。

### 5.5 文档与仓库元数据

- `openstudy-vue3-ts/README.md:22` 仍写「与 Spring Boot 3 后端配合」，实际是 FastAPI。
- `package.json:19-22` `repository` 仍指向 `https://gitee.com/y_project/RuoYi-Vue.git`。
- `SstyleREADME.md` 是一个样式提示词文档，不是项目 README，建议移入 `doc/` 或删除。

### 5.6 前端「一切皆对话」的 UI 缺口

- `AgentToolResult` / `AgentConfirmCard` 工具标签已覆盖 29/29（P1 完成）。
- 知识百科没有独立路由，是 `/front/workspace` 的 wiki tab；`sourceTypes` 六类只是 API 参数，用户可见的「按来源更新」只有文档/图片/题库/网页四项，`wiki`/`note` 无 UI。
- 资料诊疗室全部手动：上传不自动体检/不自动报告；报告 tab 打开先显示空态，必须手动点「生成智能报告」。
- 文档行没有直达「智能报告」的入口（`showSmartReport` 只有定义没有模板调用），只能进诊疗室再切 tab。
- 笔记导入资料夹：后端 `note_kb_link` 表/服务/4 端点已实现；前端入口不存在（`notes/detail.vue:243` 明确「导入知识库功能已移除」），Agent 工具也未接。

---

## 6. 测试与 CI 现状

### 6.1 后端

| 项 | 结果 |
|---|---|
| `pytest tests` | **100 passed in 9.39s，exit 0**（P0 后） |
| 裸 `pytest` | **100 passed**（pytest.ini 的 testpaths=tests；6 个 script-style 文件已 collect_ignore） |
| 历史裸 pytest 报错来源 | `test_notice.py:2` 引用不存在的 `async_session`；`_scratch/` 下 5 个临时测试 import 失败（均已清理） |
| pytest 配置 | ❌ 无 `pytest.ini` / `conftest.py` / 覆盖率配置 |
| CI | ❌ 不跑 pytest（`ci.yml:54-73` 仅 compileall + import） |
| 测试类型 | 28 个 `test_*.py` 纯函数单测；59 个 `_probe_*` 探针；12 个 `e2e_*` 手工联调脚本 |

**结论：测试资产是好的，但没接线。** 最小修复：`pytest.ini` 写 `testpaths = tests`、`pythonpath = .`，CI 加 `pytest tests -q`；把 `test_notice.py` 删除/移入 `_scratch`，裸 pytest 自然干净。

### 6.2 前端

- 无 vitest/jest；无 `test` script。
- 有自研 `check_agent_dsfree.mjs`（`npm run check:dsfree`）、2 个 `*.test.mjs`（latex-table、mindmap-data）、静态检查 `check_frontend_static.mjs`。
- `check_frontend_static.mjs` 的 `backendToolRegistry()` 存在辅助模块误判，导致 L46/L47/L48 覆盖判据降级「未验证」（`tests/check_frontend_static.mjs:1878-1896`、`:4817-4899`；代码推导，待实跑）。

### 6.3 建议的固定命令

```powershell
# 后端（在 openstudy-fastapi/）
.\.venv\Scripts\python.exe -m compileall -q app
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m ruff check app --statistics

# 前端（在 openstudy-vue3-ts/）
npm run type-check
npm run build:prod
node tests/check_agent_dsfree.mjs
```

---

## 7. 版本与文档一致性

| 位置 | 值 | 状态 |
|---|---|---|
| `VERSION:1` | 0.7.1 | 🔴 落后 |
| `openstudy-fastapi/pyproject.toml:3` | 0.7.1 | 🔴 落后 |
| `README.md:7` | 0.8.0 | ✅ |
| `openstudy-vue3-ts/package.json:3` | 0.8.0 | ✅ |
| `openstudy-fastapi/app/main.py:201,325` | 0.8.0 | ✅ |

其他：

- README `:432` 写 `api/v1` 32 个模块，实际 42 个挂载路由模块；
- README `:336` 写「20+ 个工具」，实际 29 个；
- README 0.8.0 段落未覆盖 2026-11-08～09 的规划建议/实体集/题库关联/资料智能报告；
- `openstudy-vue3-ts/README.md:22` 仍写 Spring Boot 3；
- `package.json:19-22` repository 指向 RuoYi 上游；
- `doc/代码质量提升实施方案.md` 是 2026-10-21 的历史方案，基线已过时（当时 156 个文件、无 pytest），与当前 245 个 py、100 个 pytest 测试不符；建议更新或重命名为「历史方案」。

---

## 8. 功能实现质量专项（本轮新增）

> 这一节对应「代码可读性与可维护性」之外的「功能实现是否诚实、是否完整」——LLM 评审与答辩都会问。

### 8.1 资料诊疗室

| 项 | 结论 | 证据 |
|---|---|---|
| 体检四维 | 真实、纯规则、可复现 | `document_health_service.py:537-594`；权重 30/20/25/25 |
| P0/P1/P2 | **实际只产 P1/P2**；P0 只在 `severity_order` 占位 | `document_health_service.py:532`；全文无 `_issue(..., "P0", ...)` |
| 智能报告 | 真实；不写库、无历史；默认尝试 LLM，失败回退模板并标记 `degraded.llmFallback` | `document_smart_report_service.py:228-255`；`document_clinic.py:24-59` |
| 降级诚实性 | 主路径诚实；**LLM 返回合法 JSON 但零有效改进项时，模板补齐仍标 `llmFallback: False`** | `document_smart_report_service.py:158-159, 171` |
| 「无来源不生成」 | 只在 `POST /rag/ask` 成立；智能报告不成立（无事实也给默认改进项） | `rag_query_service.py:232-236`；`document_smart_report_service.py:190-199` |
| Agent 可执行 | ❌ 无 `document_health` / `document_smart_report` / `material_organize` 工具 | `tools/__init__.py:49-146` |

### 8.2 题库 ↔ 资料夹

| 项 | 结论 | 证据 |
|---|---|---|
| 逻辑引用 | ✅ 只建 `question_bank_kb_link`，不复制题目 | `question_bank_link_service.py:94-134`；表只有 id/user_id/kb_id/bank_id/create_time |
| 知识点抽取 | ✅ 真实链路：20 题/块、最多 3 并发、≤24 实体/≤60 关系、生成主题页 | `source_entity_service.py:123-262`；`source_graph_service.py:254-278` |
| 失败可观测性 | ❌ 后台异常被 `except Exception: pass` 静默吞掉 | `question_bank_link.py:41-43` |
| 使用率 | 本地库仅 1 条关联记录；功能可用但入口隐蔽、未串进主流程 | DB 查询；前端入口 `workspace/index.vue:336-339,945-989` |
| Agent 工具 | ❌ 无 `question_bank_link` 工具 | 注册表 grep 零命中 |

### 8.3 笔记 ↔ 资料夹

| 项 | 结论 | 证据 |
|---|---|---|
| 专用导入 | 🟡 后端已实现；前端/Agent 未接 | `app/models/note_kb_link.py`、`app/services/note_kb_link_service.py`、`app/api/v1/note_kb_link.py`（4 端点） |
| 现有能力 | 笔记↔题库/题目关联 + 笔记→主题页 `ContentReference` 旁路 + 新 `note_kb_link` | `noteQuestionBank.py`、`reference_service.py`、`note_kb_link.py` |
| 图谱节点 | `source_graph_state_service` 已纳入显式关联笔记；运行库 `noteCount` 需重启后重建验证 | 代码已接入；DB 查询待验证 |

### 8.4 智能图谱

| 项 | 结论 | 证据 |
|---|---|---|
| 数据真实性 | ✅ 真实表：109 页/241 链接/704 实体/745 关系；孤儿关系 0、重名 0；682/704 实体带 doc_ids、638/704 带 chunk_ids | DB 查询 |
| 页面图性能 | ✅ 44～55 节点 / 65～142 边，0.03～0.45 秒；kb606 17 节点 0.124 秒 | 服务层实测 |
| 实体图前端 | ❌ `KnowledgeGraphSvgPanel.vue` 710 行零引用；实体图无活入口 | 全仓 grep |
| 六类图前端 | ❌ 画布用 `getWikiGraph`（page-only）；`getStudyMap` 只在来源下拉用一次；非 topic 轨迹步骤被丢弃 | `KnowledgeWikiPanel.vue:2008/1856/741-762` |
| 题源锚点 | ❌ 748 题仅 6 条 `question_source`（6 条 chunk_id 全 NULL）；两个主资料夹 `noQuestionSource=True`；kb604 默认只显示 1/6 题库 | DB 查询；`study_graph_service.py:481` |
| 笔记节点 | ❌ 34 条有效笔记全未进图；noteCount 恒 0；唯一 note 相关引用指向已删文档 664 | `study_map_service`；DB 查询 |
| 边 ID 稳定性 | ✅ `e:{kind}:{sha1(source->target)[:16]}` 跨请求稳定；回归测试覆盖 | `study_map_service._add_edge` |
| 规模化 | ❌ 页/链接查询无 LIMIT；`_has_pages` O(来源×页)；无物化快照 | `study_graph_service.py:371`、`wiki_service.py:2253`、`source_graph_state_service.py:38-48` |
| 来源口径 | ⚠️ 23 页 `generated_by=source:bank`、`source_doc_ids/source_refs=[]`、正文 32–38 字符；「每小节落真实 chunk」只对文档型页面成立 | DB 查询；`source_graph_service.py:129-176` |

### 8.5 结论

- **可以对外说**：资料体检/智能报告/题库关联/知识图谱都有真实实现，不是 PPT 功能；体检纯规则可复现，智能报告有降级标记。
- **不能对外说**：不能把「自动闭环」「全产品无来源不生成」「P0/P1/P2 三级问题」「笔记已可导入资料夹」「实体图已产品化」写成既成事实。
- **需要补的**：一键编排（上传→体检→报告）、报告持久化、P0 规则或改口径、降级标志修复、题库抽取失败回传、笔记导入、实体图入口/下线、题源锚点补建。

---

## 9. LLM 评审会怎么查（摘要）

> 完整应对见 `LLM技术实现质量20%审查应对手册.md`。

一个 LLM 评审不会逐行读完 27 万行代码；它会做「高信号抽样」：

1. **看仓库结构**：根目录是否有 `README`、`ARCHITECTURE`、`Makefile`、`ruff.toml`、`pytest.ini`、`.github/workflows`。
2. **看配置**：`package.json` scripts、`pyproject`、`requirements`、`tsconfig`、lint/format/test 配置。
3. **看门禁**：CI 是否跑 lint/test/build；type-check 是否可执行。
4. **看大文件/长函数**：`questions.py`、`rag.py`、`loop.py`、`workspace/index.vue`、`QuestionBuilder.vue` 一眼可见。
5. **搜坏味道**：`TODO`、`console.log`、`print(`、`except:`、`any`、`@ts-ignore`、注释掉的路由。
6. **看死代码/仓库卫生**：`_scratch`、`build-*.log`、`type-errors.txt`、`300`、`audit_ws_summary.json`、`.bak`。
7. **看测试**：有没有 `pytest.ini`、`tests/`、CI test step；能否一条命令跑。
8. **看版本/文档**：VERSION 与 README/package 是否一致；README 是否说 Spring Boot 而代码是 FastAPI。
9. **看功能与口径是否一致**：说「没有悬浮助手」但代码里有 `.float-btn`；说「笔记可导入资料夹」但代码没有表/端点；说「建议不是任务」但旧 `StudyPrescriptionPanel` 还有勾选完成。这些是**最容易被 LLM 抓的「说法 vs 代码」矛盾**。
10. **看 AI 工具使用痕迹**：`doc/dev-process/` 日志、session、commit 记录、工具调用统计；是否可交叉验证。

**P0 后仍然最容易被抓的 5 个点：**

1. `npm run type-check` 从「必崩」变成「能跑但 1,980 条存量错误」——比之前诚实，但离绿还有距离；
2. `npm run lint` 是 0 errors / 3,362 warnings 的 warn-only 基线，warning 数量会被评审追问；
3. `package-lock.json` 被前端 .gitignore 忽略，CI 目前用 `npm install` 兜底，锁文件口径未完全统一；
4. 后台动态菜单页（system/monitor/courses 等）仍有历史类型错误与「教师/学生」字段，需产品确认去留；
5. 「说没有悬浮助手/建议不是任务/笔记没做」曾经与代码残留不一致——本轮已清到 `rg "float-btn"` 0，但旧文档若未同步会再次制造矛盾。

---

## 10. 清理路线图（P0 / P1 / P2）

### P0（1～3 天，低风险、高杠杆，不碰业务逻辑）— 2026-11-09 已执行第一批

1. **版本统一**：`VERSION`、`pyproject.toml` 改 0.8.0（或统一升 0.9.0）。
2. **复活 type-check**：已锁 `typescript@5.3.3` + Node heap 8GB，工具不再崩溃；下一步按 P1 压存量错误。
3. **仓库卫生**：删 `300`、`audit_ws_summary.json`、`type-errors.txt`、`ts_errors.txt`、25 个 `.bak`；`.gitignore` 补 `_scratch_041/`、`_scratch_english_A/`、`openstudy-fastapi/_scratch/`、`audit_ws_summary.json`、`300`、`*.bak*`；`doc/competition/码道架构图/` 决定入库或 ignore。
4. **删确定死代码**：`utils/generator`、`PageWithFilter`、17 个孤儿组件、旧首页、dictation 链路、chats.vue、`test_notice.py`、`test_ds_free.py`、`favorites.py`、`notice_repo.py`、`check_images.py`、`check_notice.py`（先确认无启动脚本引用）。
5. **清悬浮助手残留**：删 `AiAssistant/index.vue:511-580` 的拖拽逻辑、`1379-1431` 的 `.float-btn`/`.assistant-entry` 死样式；删 `FrontSidebar:859-868` 死样式；把 `layout/front.vue:152-168` 注释改成「全局 AI 助手抽屉」。
6. **加 pytest 配置**：`pytest.ini`（`testpaths = tests`、`pythonpath = .`、`--strict-markers`）+ `conftest.py`；CI 加 `pytest tests -q`。
7. **加 lint 基线**：`ruff.toml`（先开 `E9/F63/F7/F82/F401/F841/E722`，ignore `B008/E501/E402`）；前端加 ESLint flat config + Prettier，先 `warn` 不阻塞。
8. **5 处裸 except 清零**：`auth.py:101`、`ai.py:405`、`notes.py:1103/1138`、`notice_front.py:68`。

**验收标准（修订后）**：`git status` 仅剩用户文件；`pytest tests` 100 passed；`ruff check app --select E9,F63,F7,F82` exit 0；`npm run lint` 0 errors；`npm run build:prod` exit 0；VERSION 全一致；全仓 grep `float-btn` 0 命中。**`npm run type-check` 仍会失败（3,218 条存量错误），列入 P1 首个专项，不伪装为 P0 已完成。**

### P1（1～2 周，结构化改进，需测试保护）— 下一步

1. ✅ 已提取 `app/utils/pagination.py`；`api/v1` 的 `count_query = select(func.count())...` 分页样板已全部清零。
2. ✅ 4 个 ORM 模型已从 API 迁入 `app/models/`；alembic migration 待补。
3. `requirements.txt` 由 `poetry export` 生成，消除双源漂移。
4. 🟡 `console.log` Top3 已清（`QuestionBuilder` 25 / `PracticeComponent` 14 / `CommentModal` 15）；全前端仍剩 56 处，`any` 继续按规则清理。
5. 为 `agentDsFree.ts` 与 `loop.py` 的镜像常量写一致性契约测试（`SAME_CALL_LIMIT` / `DEAD_LOOP_STRIKES` / `FORMAT_FIX_LIMIT`）。
6. ✅ 已完成：29 个工具标签、5 个角色白名单、5 个产物/快照工具 `write_operation=True`；`needs_confirmation` 按工具语义保留。
7. 修智能报告降级标志边界（`document_smart_report_service.py:158-159`）；给体检 P0 规则或把「P0/P1/P2」改成「P1/P2」。
8. 题库关联后台抽取失败改为回传 `degraded`，前端提示「知识点抽取失败，可重新更新」。
9. ✅ 覆盖率基线已加：`pytest tests --cov=app/services --cov-report=term-missing` → **19%**；只报数字不设门槛。

### P2（2～4 周，债务减量）— 后续

1. 拆分 `workspace/index.vue`（6,512 行）、`QuestionBuilder.vue`（5,445 行）、`loop.py` 的 `run_agent_stream`（按工具解析/护栏/事件发射拆模块）。
2. `questions.py` / `rag.py` 业务下沉 service，路由只留参数/权限/响应。
3. 合并 OCR 双实现、上传/预览组件族；建 `useFileUpload`、`useOcr` 等 composable。
4. `any` 减量从 `permission.ts`、`utils/index.ts` 开始，每文件小步类型化。
5. **图谱四套服务收口**：统一 `GraphNode/GraphEdge` 契约；`knowledge_map_service` 下线或标 deprecated；`knowledge_graph` 补实体图入口或删除 `KnowledgeGraphSvgPanel`；`study_map` 的六类图接到前端画布并明确主视图/建议图分工；边 ID 改为内容派生；页/链接查询加 limit 或物化快照。
6. **笔记导入资料夹**：✅ 已完成：`note_kb_link` 表 + 4 端点 + service + `source_graph_state` + Agent 工具 + 笔记详情「加入资料夹」入口。
7. **资料诊疗室 Agent 化**：补 `document_health`、`document_smart_report`、`material_organize_preview` 三工具，挂 `kb`/`general` 角色。
8. 建立 `docs/quality/`：质量报告、死代码台账、覆盖率趋势、评审指南。

---

## 11. 证据附录

```powershell
# 版本
Get-Content VERSION
Select-String -Path openstudy-fastapi/app/main.py -Pattern 'version="'
Select-String -Path openstudy-vue3-ts/package.json -Pattern '"version"'

# 前端类型检查（P0 后：不再崩溃，但仍有 1,980 条存量错误）
cd openstudy-vue3-ts; npm run type-check

# 后端测试（P0 后）
cd openstudy-fastapi; .\.venv\Scripts\python.exe -m pytest tests
# → 100 passed in 9.39s, exit 0

# ruff 语法门禁（P0 后）
.\.venv\Scripts\python.exe -m ruff check app --select E9,F63,F7,F82
# → All checks passed

# ESLint/Prettier 基线
cd ..\openstudy-vue3-ts; npm run lint
# → 0 errors, 3232 warnings

# 死代码引用检查示例
rg "utils/generator" openstudy-vue3-ts/src    # 0
rg "PageWithFilter" openstudy-vue3-ts/src     # 0
rg "float-btn" openstudy-vue3-ts/src          # 仅 AiAssistant 死样式
rg "StudyPrescriptionPanel|StudyPackPanel|StudyPackDialog" openstudy-vue3-ts/src  # 仅自身

# 仓库卫生
git status --porcelain
```

**文件行号口径说明：** 本清单中「物理行数」用 `[System.IO.File]::ReadAllLines().Length`（含空行）；部分旧文档使用 `Measure-Object -Line`（不含空行），因此会出现 3,462 vs 4,027、5,912 vs 6,512 的差异，属统计口径而不是代码变化。
