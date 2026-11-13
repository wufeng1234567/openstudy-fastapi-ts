# OpenStudy 技术实现质量 20% · P0–P2 执行方案

> 目标：围绕华为开发者大赛「技术实现质量 20%：工具使用是否规范、代码可读性与可维护性」，让 LLM 评委在 30 秒内看到可打开的架构、质量证据、可复跑命令和真实边界。
> 基线日期：2026-11-12
> 适用：评审材料、答辩、后续工程迭代
> 约束：CodeArts 开发不额外补做；按管理员口径，使用云码道发布软件即视为使用开发工具，重点放在 GitCode 仓库与工程证据。

---

## 0. 先看结论

LLM 评审不会逐行读完 17 万行代码。它主要做：

1. 扫根目录和文件树，找 README、ARCHITECTURE、Makefile、CI、锁文件、垃圾文件；
2. 跑最显眼的命令：pytest、lint、build；
3. 抽大文件、坏味道搜索（TODO、console.log、any、裸 except、死代码）；
4. 对照文档承诺和代码事实，检查口径一致性；
5. 找 AI 工具使用留痕（commit、日志、会话、memory）。

所以策略必须是：

> **真实清理 + 证据层 + 诚实边界，三者同时做。**

---

## 1. 手册完成度（基于 2026-11-12 仓库事实）

### 1.1 已经完成或基本完成

| 项目 | 证据 | 判断 |
|---|---|---|
| 版本统一 | `VERSION`、`pyproject.toml`、`package.json`、`main.py` 均为 0.8.0 | ✅ P0 |
| 后端 pytest 配置 | `pytest.ini`、`conftest.py`、`asyncio_mode=auto`；本次实测 **109 tests collected** | ✅ P0 |
| 后端语法门禁 | `ruff check app --select E9,F63,F7,F82`：All checks passed | ✅ P0 |
| 编译与导入 | `compileall` exit 0；`from app.main import app` 可装配 | ✅ P0 |
| 前端 lint/format 工具 | `eslint.config.js`、`.prettierrc.json`、`package.json` scripts 存在 | ✅ 工具已接电 |
| 前端构建 | `npm run build:prod` exit 0 | ✅ |
| CI 存在 | `.github/workflows/ci.yml` 有 3 个 job；此前有 runner 成功记录 | 🟡 有流程，非强门禁 |
| 死代码清理第一批 | 17 个 Vue 组件、旧首页/听写/私信、`utils/generator` 等已删 | ✅ P0 |
| 产品口径 | README/系统介绍已改为「信息来源处理系统」，不是学生刷题平台 | ✅（部分旧文档仍有旧口径） |

### 1.2 当前真实差距

| 差距 | 事实 | 影响 |
|---|---|---|
| 文档数字不一致 | `quality-report.md` 写 lint 3,277；`code-quality-review.md`/`llm-handbook-review.md` 写 3,214；应对手册自身把「口径一致性」列为评审重点 | 评委一搜索就发现矛盾，直接扣可维护性 |
| lint 仍是 warn-only | 当前实际运行约 **0 errors / 4,077 warnings**（以质量报告当前值为准） | 需要建立 warning 预算与递减计划 |
| 仓库有已跟踪生成物 | `.gitignore` 已写忽略，但 `openstudy-fastapi/tests/_evidence/`（74 文件）、`_ui_evidence/`（7）、`doc/competition/码道架构图/`（23）、`doc/competition/_preview/`（10）等历史上已入库；根目录还有 5 个 `_scratch*`、13 个 `_tc*.log`、`_build_err.log`，前端约 40 个 `build-*.log`；双锁 `package-lock.json` + `pnpm-lock.yaml` | 「规则形同虚设」，LLM 会认为仓库卫生不可信 |
| ruff 全量未清零 | 语法门禁 `E9,F63,F7,F82` 通过；全量 `ruff check app` 仍有约 **115 errors**（107 F401 + 8 F841） | 语法门禁可过，但不等于全量 lint 干净 |
| 根目录标准文件缺失 | 无 `ARCHITECTURE.md`、`CONTRIBUTING.md`、`SECURITY.md`、`Makefile`、`.editorconfig`、`.gitattributes` | 质量项目第一眼不完整 |
| 文档偏介绍、证据分散 | 8 份质量文档中多份是系统介绍/自评/对文档的 review；最硬的 `doc/闭环检查`、`ruoyi-cleanup-report` 无索引 | 评委找不到真证据 |
| README 偏营销 | 根 README 240 行，质量证据/CI/死代码台账/架构没有入口 | 30 秒内看不到质量 |
| CI 不是强门禁 | 前端 `npm install` 不是 `npm ci`；覆盖率仅报告 | 「有 CI」不等于「有门禁」 |
| 迁移/回滚 | `alembic.ini` 指向不存在的 `alembic` 目录；实际靠 `init_db` + 手写 SQL；无回滚 Runbook | 运维完整性不足 |

### 1.3 手册 P0/P1/P2 的完成度判断

| 级别 | 完成度 | 说明 |
|---|---:|---|
| P0（门禁/卫生/版本/裸 except） | **约 75%** | 版本、pytest、ruff、构建、第一批死代码已完成；但 Git 已跟踪生成物未脱管、证据数字不统一、根标准文件缺失 |
| P1（结构债务/文档/CI） | **约 40%** | 工具标签、分页、ORM 迁移、覆盖率基线有进展；ARCHITECTURE/CONTRIBUTING/SECURITY/ADR/测试分层/CI 强门禁未完成 |
| P2（拆分/类型化/债务减量） | **约 20%** | 笔记导入资料夹、部分图谱契约有进展；巨型文件、图谱四套服务、any/console/覆盖率仍未完成 |

> 不要对外报「P0 全部完成」。按 LLM 评审口径，当前更像「P0 第一批完成、证据层未收口」。

---

## 2. P0 / P1 / P2 目标

### P0（1–3 天，必须完成，低风险高杠杆）

**P0-1 Git 卫生与可复现仓库**

- 保留并提交 `.gitignore` 新规则：小红书配图、压缩包、智能体核心知识梳理、智能整理测试集、竞赛 `_preview`、pip 临时目录、前端探测产物。
- 对已跟踪但应忽略的文件执行 `git rm --cached`（不删除本地文件）：
  - `openstudy-fastapi/tests/_evidence/`
  - `openstudy-fastapi/tests/_ui_evidence/`
  - `openstudy-fastapi/tests/.e2e_agent_mem_baseline`
  - `doc/competition/码道架构图/`
  - `doc/competition/_preview/`
  - `startup-scripts/package-lock.json`
  - `openstudy-vue3-ts/tests/.tmp_p_none.txt`、`.tmp_p_norm.txt`、`_served.js`
- 在 CI `repo-hygiene` 加入“已跟踪生成物”断言，防止规则写了但文件又入库。
- 验收：`git status` 只剩用户本地资料；`git ls-files` 不再出现上述路径；`git check-ignore` 验证小红书素材被忽略。

**P0-2 质量证据单一来源**

- 统一基线 commit 和数字：`quality-report.md` 重新跑一遍并写命令输出；
- 以**一次真实运行**为准：pytest 数量、ruff、lint warnings、build、coverage；
- 创建 `doc/quality/dead-code-ledger.md`（或先放当前目录，后续迁移），逐项记录删除文件、引用核查、commit、行数；
- 把 `doc/功能迭代与代码质量/README.md` 改成「30 秒评审证据地图」：每行 = 想确认什么 → 文件 → 一句话结论 → 复跑命令；
- 删除/归档 `code-quality-review.md`、`llm-handbook-review.md` 这类“对文档自身的 review”，避免循环自证。

**P0-3 根目录标准文件**

新增：

- `ARCHITECTURE.md`：一页架构图、前端/后端分层、Agent/SSE/RAG 主链路、数据边界、已知边界；
- `CONTRIBUTING.md`：运行方式、提交规范、测试/质量门禁、目录约定；
- `SECURITY.md`：密钥管理、`.env` 规则、漏洞报告渠道、越权/PII 修复记录入口；
- `Makefile`（或 `scripts/` + `.bat`）：`dev / test / lint / build / verify / migrate / seed / backup / restore`；
- `.editorconfig`、`.gitattributes`（LF、二进制/LFS 约定）。

**P0-4 一条命令验证**

新增 `scripts/verify-quality.bat`（Windows `.bat`，ASCII）：

- 后端：compileall → ruff 语法门禁 → pytest；
- 前端：lint → build:prod；
- 仓库：`git status --porcelain`、`git ls-files` 敏感/生成物断言；
- 输出一份 `doc/quality/latest-verification.txt`（或 CI artifact）。

**P0-5 CI 接电**

- 前端 `npm install` 改 `npm ci`（只保留一个锁文件，与 pnpm 的关系先定清楚）；
- 覆盖率、lint warning 至少设“不得新增”或预算阈值；
- 增加“版本三处一致”和“已跟踪生成物”检查。

**P0 交付物**

- 干净的 `git status`；
- 新的 `quality-report.md`（真实命令 + 真实数字）；
- `dead-code-ledger.md`；
- `ARCHITECTURE.md`、`CONTRIBUTING.md`、`SECURITY.md`、`Makefile`、`scripts/verify-quality.bat`；
- README 顶部质量证据区。

### P1（1–2 周，结构化补齐）

1. **文档分层**
   - `doc/index.md`：评委唯一入口；
   - `doc/feature-map.md`：15 个功能域 → 路由 → 服务 → 测试/截图证据；
   - `doc/architecture/api-data-model.md`：545 routes、80 ORM 表、29 Agent 工具契约、认证约定；
   - `doc/architecture/adr/0001...`：向量库/embedding、RAG、迁移方案等关键决策；
   - `doc/quality/test-strategy.md`：pytest 109、覆盖率 19%（历史值，需修 coverage 复跑）、前端测试规划；
   - `doc/operations/deploy.md`：compose、启动脚本、环境变量、备份/恢复、回滚。

2. **文档与代码口径统一**
   - 根 README、HANDOFF、ROADMAP、CORE-FLOW、ITERATION-PLAN 统一到「信息来源处理系统」；
   - CHANGELOG 补 0.8.0 后 48 个提交；
   - 所有质量文档统一引用同一基线 commit 和同一组数字。

3. **测试与 CI**
   - 后端测试目录分 `unit/`、`integration/`、`contract/`；
   - 前端增加 Vitest 单元测试与 Playwright smoke；
   - CI 增加前端测试 job、依赖漏洞扫描、版本一致性、覆盖率报告 artifact；
   - `requirements.txt` / `pyproject.toml` / 锁文件收敛为单一可复现来源。

4. **工程结构**
   - 根脚本归入 `scripts/`，根目录只留薄入口；
   - 增加 `.pre-commit-config.yaml`（ruff、eslint、prettier、secret scan）；
   - `doc/adr/` 与 `doc/architecture/` 建目录和模板。

5. **P1 交付物**
   - 评审可在 `doc/index.md` 一次跳转到架构、功能、质量、测试、部署、安全；
   - `verify-quality.bat` 可本地和 CI 复跑；
   - 文档数字无冲突。

### P2（2–4 周，债务减量）

1. **巨型文件拆分**：`QuestionBuilder.vue`、`loop.py`、`questions.py`、`rag.py`、`KnowledgeWikiPanel.vue` 等按 views/components/composables/utils 拆；
2. **图谱四套服务收口**：统一 `GraphNode/GraphEdge`、稳定边 ID、前端统一图入口；
3. **类型与坏味道**：any/console.log/重复代码按目录台账清理；
4. **测试覆盖率**：19% → 30% → 40%，优先服务层和 Agent 工具契约；
5. **仓库体积**：大截图/过程证据移出 Git 或用 Release 附件/LFS；`doc/` 只保留可引用证据；
6. **可观测与运维**：健康检查、结构化日志、错误追踪、回滚 Runbook。

**P2 不追求一次性完美**：目标是“有台账、有下降趋势、有复跑证据”。

---

## 3. 一个完整、有质量的项目工程结构

### 3.1 根目录

```text
README.md                 # 30 秒定位 + 质量证据入口 + 快速开始
ARCHITECTURE.md           # 一页架构、分层、主链路、边界
CONTRIBUTING.md           # 开发/提交/测试/评审规则
SECURITY.md               # 密钥、漏洞报告、权限边界
CODE_OF_CONDUCT.md         # 协作规范（加分）
LICENSE                   # 许可证
CHANGELOG.md              # 版本变更
VERSION                   # 单一版本源
Makefile / Taskfile       # 统一命令入口
.editorconfig             # 编辑器一致性
.gitattributes            # 换行/二进制/LFS 约定
.gitignore                # 生成物、密钥、本地素材
.env.example              # 环境变量模板（不含真实密钥）
docker-compose.yml        # 本地/部署拓扑
Dockerfile(s)             # 可构建镜像
.github/workflows/ci.yml  # CI 门禁
.github/ISSUE_TEMPLATE/   # 协作模板（加分）
.github/PULL_REQUEST_TEMPLATE.md
scripts/                  # bootstrap/dev/test/lint/build/verify/release/backup
doc/                     # 文档总入口
```

### 3.2 前端工程结构

```text
openstudy-vue3-ts/
  src/
    api/            # 按业务域分文件，类型化请求/响应
    assets/         # 静态资源
    components/     # 通用展示组件
    composables/    # 状态/副作用复用
    layouts/        # 页面布局
    router/         # 路由与守卫
    stores/         # Pinia
    styles/         # 全局样式/变量
    types/          # 领域类型
    utils/          # 纯函数工具
    views/          # 页面编排（不放大段业务逻辑）
  tests/
    unit/           # Vitest
    e2e/            # Playwright smoke
  public/
  .env.development / .env.example
  vite.config.ts
  tsconfig*.json
  eslint.config.js
  .prettierrc.json
  package.json
  package-lock.json（只保留一个锁文件）
```

判断标准：`views` 只编排，`components` 展示，`composables` 状态/副作用，`utils` 纯函数；单文件建议 ≤1000 行（当前重构目标）。

### 3.3 后端工程结构

```text
openstudy-fastapi/
  app/
    api/v1/          # 路由：参数/权限/响应，业务下沉 service
    core/            # 配置、日志、安全、异常
    models/          # ORM 模型
    schemas/         # Pydantic 模型
    services/        # 业务服务
    repositories/    # 数据访问（可选）
    db/              # 会话/初始化
    migrations/      # Alembic 版本化迁移
    workers/         # 后台任务
    utils/           # 纯工具
  tests/
    unit/
    integration/
    contract/
  scripts/
  pyproject.toml / requirements.lock
  pytest.ini
  ruff.toml
  Dockerfile
```

判断标准：API 薄、service 厚、model/schema 清晰；数据库变更必须走可回滚 migration；异常有日志和降级说明。

### 3.4 质量与运维证据

```text
doc/
  index.md                 # 唯一入口：想确认什么→打开哪个文件
  feature-map.md           # 功能域→代码→证据
  architecture/
    api-data-model.md
    adr/0001-*.md
  quality/
    README.md              # 30 秒证据地图
    quality-report.md      # 命令→输出→结论
    dead-code-ledger.md
    test-strategy.md
    verification/          # 闭环/P0/P1/P2 台账 + evidence
  operations/
    deploy.md
    rollback.md
  process/                 # 开发过程留痕（脱敏）
```

### 3.5 必须有的质量门禁

- 一条命令：`verify-quality.bat`（或 `make verify`）；
- `pytest` + 覆盖率报告；
- `ruff`（语法/未定义名先清零）；
- `eslint` + `prettier --check`；
- `build:prod`；
- 密钥扫描、`.env`/依赖目录检查、已跟踪生成物检查；
- 版本三处一致；
- CI 在 PR/push 上真实执行；
- 发布前质量报告归档。

---

## 4. 评委 30 秒证据地图（目标）

| 评委想确认 | 打开文件 | 一句话结论 | 复跑命令 |
|---|---|---|---|
| 架构是什么 | `ARCHITECTURE.md` | 前端 Vue3/FastAPI/Postgres，Agent+RAG 主链路 | — |
| 代码质量真的如何 | `doc/quality/quality-report.md` | pytest/ruff/lint/build 的真实输出 | `scripts/verify-quality.bat` |
| 有没有死代码/清理证据 | `doc/quality/dead-code-ledger.md` | 文件、行数、0-import 核查、删除 commit | `git log --oneline` |
| CI 真的跑吗 | `.github/workflows/ci.yml` + run 链接 | 3 jobs | Actions 页面 |
| 工程规范 | `CONTRIBUTING.md` / `SECURITY.md` / `Makefile` | 提交、测试、密钥、命令 | — |
| 文档是否可信 | `doc/index.md` | 统一基线/统一数字/已知债务 | — |

---

## 5. 执行顺序与验收

### 第 1 天（P0）

1. 提交 `.gitignore`（已完成）；
2. `git rm --cached` 已跟踪生成物；
3. 重跑 `quality-report` 命令并统一数字；
4. 建 `ARCHITECTURE.md`、`CONTRIBUTING.md`、`SECURITY.md`；
5. 建 `scripts/verify-quality.bat`。

### 第 2–3 天（P0 收口）

6. 根 README 加质量证据区；
7. 建 `dead-code-ledger.md`；
8. CI 增加版本一致性、已跟踪生成物断言，修正 `npm ci`；
9. 评审自测：按手册第 2 节 10 步走一遍，记录证据。

### 第 1–2 周（P1）

10. `doc/index.md`、功能地图、API/数据模型、ADR、测试策略、部署/回滚；
11. 测试目录分层、前端最小测试、覆盖率报告；
12. 统一旧文档口径并归档重复文档。

### 第 2–4 周（P2）

13. 巨型文件拆分；
14. 图谱服务收口；
15. any/console 递减；
16. 截图/大文件移出 Git 或 Release 附件。

**P0 验收线（未达到就不宣称完成）：**

- `git status` 干净（只允许用户确认的本地文件）；
- `git ls-files` 无已跟踪生成物；
- `pytest`、`ruff`、`build:prod` 可复跑；
- README 首屏 6 个证据链接全部可打开；
- 文档中 lint/commit 数字只有一个版本。

### P0 执行记录（2026-11-12）

- ✅ `.gitignore` 已加入小红书素材、本地整理资料、竞赛预览、pip/前端临时产物规则；
- ✅ `git rm --cached` 已脱管 `_evidence`、`_ui_evidence`、竞赛预览、临时文件；`git ls-files` 生成物检查为 0；
- ✅ 新增 `ARCHITECTURE.md`、`CONTRIBUTING.md`、`SECURITY.md`、`Makefile`、`.editorconfig`、`.gitattributes`；
- ✅ 新增 `scripts/verify-quality.bat`；实测后端 compile/ruff/pytest、前端 lint/build 通过；
- ✅ 新增 `doc/README.md` 文档总索引、`dead-code-ledger.md`，根 README 增加质量证据区；
- ✅ CI 已增加 frontend lint 与已跟踪生成物断言；前端改为唯一 `package-lock.json` + `npm ci`（`pnpm-lock.yaml` 已退出 Git 跟踪）。

### P1 执行记录（2026-11-12）

- ✅ 文档总索引、功能地图、API/数据模型、测试策略、质量/运维入口、ADR 已建立；
- ✅ 前端已有 `npm run test:unit`：2 个 Node 测试、29 项断言通过（mindmap 15 + table 14）；
- ✅ `.pre-commit-config.yaml`、测试目录约定、`doc/operations/rollback.md` 已落盘；
- ✅ CI 已加入前端单元测试与版本一致性检查；
- ✅ 前端唯一 `package-lock.json` + CI `npm ci`；`pnpm-lock.yaml` 已退出 Git；
- 🟡 真实 Vitest/Playwright、覆盖率阈值仍在 P1。

### P2 执行记录（2026-11-12）

- ✅ `QuestionBuilder.vue` 从 2,337 行降到 **1,382 行**（Batch 1 + Batch 2）：AI 结果解析/预览/导入/丢弃抽入 `useQuestionBuilderAiResult.ts`，AI 生成执行链抽入 `useQuestionBuilderAiGenerate.ts`，提示词历史抽入 `useQuestionBuilderPromptHistory.ts`，AI 配置/资料上下文抽入 `useQuestionBuilderAiConfig.ts`，题目编辑动作抽入 `useQuestionBuilderEdit.ts`，AI 弹窗打开/快捷键抽入 `useQuestionBuilderAiDialog.ts`；build 通过，studio 页面 `.question-panel`/`.edit-panel` 正常，console/pageerror 0；
- 🟡 `KnowledgeWikiPanel.vue` 1,996 行（Batch 1 + Batch 2）、`useAgentChat.ts` 1,404 行（Batch 1）、`useQuestionPractice.ts` 1,442 行（Batch 2）；
- 🟡 后端 `questions.py` 2,571 行；`rag.py` 2,299 行；`wiki_service.py` 1,628 行；`loop.py` 1,882 行（Batch 3/4/6/8/9/11/13/15/16/17/18/19/22/23），按技术债务登记继续。

---

## 6. 待拍板事项

1. `doc/screenshots/` 是否全部保留在 Git：建议只保留 README 实际引用的 6 张，其余移 Release/本地；
2. `doc/competition` 的 PDF/PPT 是否作为提交物保留：建议保留成品，忽略预览/缓存；
3. 是否把现有 `doc/` 全量迁移到 `doc/quality` 或 `doc/architecture`：建议先新增 `doc/README.md` 做入口，不一次性搬 588 个路径，避免断链；
