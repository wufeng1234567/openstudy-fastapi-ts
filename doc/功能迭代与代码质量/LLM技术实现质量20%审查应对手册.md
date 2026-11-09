# LLM 技术实现质量 20% 审查应对手册

> 文档版本：v2.0（2026-11-09 修订）
> 适用场景：评审/答辩中有一项「技术实现质量 20%：工具使用是否规范、代码可读性与可维护性」，评审方可能由 LLM 辅助或完全由 LLM 做初筛。
> 本文回答两个问题：**同行 LLM 会怎么检查？我们怎么应对？**
> 基线：`main @ 58f12c7`（2026-11-09）。配套证据见 `OpenStudy-代码质量审计与无用代码清理清单.md`。
> 本轮修订重点：补充「产品口径 vs 代码实现」一致性检查、智能图谱可用性答辩口径、资料诊疗室/智能报告/笔记导入的资料域问答，并纠正旧文档的「全局悬浮助手」写法。

---

## 0.1 下一阶段目标任务（2026-11-09）

> 触发条件：代码质量文档的 P0/P1/P2 可执行动作已进入收尾，下一步把本手册从「答辩材料」升级为「可执行评审清单」；type-check 存量仍作为公开已知债务保留。

| 级别 | 目标任务 | 验收标准 |
|---|---|---|
| P0 | 证据数字统一：29 个 Agent 工具、98 pytest、3,214 lint warnings、2,993 type-check errors、19% coverage | 全文搜索无 28 工具/102 tests/3,218 errors 等旧数字；与 `quality-report.md` 一致 |
| P1 | 把第 2 节 7 步检查扩成 10 步可执行清单：根目录/README/scripts/命令/大文件/坏味道/测试/版本/死代码/口径一致性 | 每一步都有「看什么 → 怎么跑 → 期望结果 → 不通过怎么解释」 |
| P1 | 增加评审模拟脚本入口与证据文件索引 | 评审可依次打开 `quality-report.md`、测试/构建命令、P0/P1/P2 台账 |
| P2 | 增加答辩 Q12–Q14：type-check 存量、笔记导入资料夹、图谱四套服务 | 每个问题都有事实数字、边界说明、下一步动作，不空泛 |
| P2 | 与本目录三份文档交叉链接，统一 B/P 编号 | README 可一键跳转到审计、方案、答辩三部分 |

---

## 0. 先校准：LLM 评审不是在「读全部代码」

LLM 评审的上下文有限，它不会逐行读 27 万行代码。它实际做的是**高信号抽样 + 关键词搜索 + 文件树扫描 + 配置检查**。因此：

> **它看到的不是「我们真实的质量」，而是「仓库里可被快速检索到的质量证据」。**

这意味着两件事：

1. 只改代码、不整理证据，评审看不见；
2. 只做表面文档、代码里全是 `except:` / `console.log` / 死文件，评审一搜就穿帮。

**正确策略：真实清理 + 评审友好的证据层，两者同时做。**

> **本轮特别提醒（2026-11-09）：** 旧文档里的「全局悬浮助手」是错误描述。真实入口是**侧边栏左上角品牌行的 OpenStudy 助手按钮 → 右侧抽屉**；代码里仍残留 `.float-btn { position: fixed; ... }` 和约 70 行拖拽逻辑（`AiAssistant/index.vue:511-580, 1402-1431`），属于要清理的死代码，不是活功能。LLM 评审如果先读旧文档再 grep 代码，会立刻发现「说没有悬浮球、但代码里有 fixed 圆形按钮样式」的矛盾；本手册后续统一按新口径写。

---

## 1. 「技术实现质量 20%」可能怎么拆

不同比赛/评审的细则不同，但按常见拆法，20 分可能分成：

| 子项 | 分值（假设） | LLM 会看什么 |
|---|---:|---|
| 工具使用规范性 | 10 | 是否有 lint/format/type-check/test/CI；是否一条命令可跑；是否有开发工具留痕（CodeArts/Agent 会话、commit、日志）；是否有密钥/垃圾文件 |
| 代码可读性与可维护性 | 10 | 目录结构、命名、注释、类型、函数/文件长度、重复代码、分层、死代码、异常处理、文档与代码一致性 |
| 本轮新增：功能口径一致性 | 0（通常并入可维护性） | 文档说「没有悬浮助手」但代码有 `.float-btn`；说「笔记可导入资料夹」但无表/端点；说「建议不是任务」但旧 `StudyPrescriptionPanel` 有勾选——LLM 最容易被这类「说法 vs 实现」矛盾说服扣分 |

也可能把「工具使用」理解为「AI 编码工具使用是否规范」而不是「工程工具链」。**两种解释都要覆盖：**

- **工程工具链**：ruff、eslint、prettier、pytest、vitest、CI、Makefile、pre-commit。
- **AI 工具使用**：`doc/dev-process/logs/` 5 天日志、6 份会话、91 份 memory、3,214 次工具调用、50 次 commit、186 个文件改写；会话 ID/时间戳/工具调用记录/提交记录可交叉核对。这是 OpenStudy 的强项，不要埋没。

---

## 2. 同行 LLM 的 10 步检查流程（模拟）

### 第 1 步：扫根目录与文件树

它会先看：

```
README.md
ARCHITECTURE.md? (没有)
Makefile? (没有)
ruff.toml / pytest.ini / .eslintrc / .prettierrc? (没有)
.github/workflows/ (有)
docker-compose.yml (有)
VERSION (0.7.1)
doc/
_scratch*/
build-*.log
type-errors.txt
```

**它得出的第一印象：**「项目有文档、有 CI，但工程门禁文件缺失，根目录有垃圾。」

### 第 2 步：读 README 和子 README

它会看：

- 主 README 说 0.8.0、FastAPI、20+ 工具、32 个模块；
- 前端 README 说「与 Spring Boot 3 后端配合」；
- `package.json` repository 指向 RuoYi-Vue。

**它得出的判断：**「文档与代码不一致，维护者可能没有认真收尾。」

### 第 3 步：检查 scripts / 依赖 / 配置

- `package.json` 有 `type-check`，但没有 `lint`/`test`/`format`；
- `pyproject.toml` 有 pytest dev 依赖，但 `requirements.txt` 没有；
- 没有 `pytest.ini`、没有 `ruff.toml`、没有 Makefile；
- 双锁文件（`package-lock.json` + `pnpm-lock.yaml`）。

**它得出的判断：**「工具链不成体系。」

### 第 4 步：实际跑「最显眼的命令」

- 跑 `npm run type-check` → **不再崩溃**（TypeScript 已锁 5.3.3、Node heap 8GB），但会报出 **2,993 条存量类型错误**（P1 第一批收敛后；初始 3,218）；
- 跑 `pytest tests` → **99 passed**（P0 后）；
- 跑 `npm run lint` → **0 errors / 3,214 warnings**（warn-only 基线）；
- 跑 `npm run build:prod` → 成功（exit 0）。

**它得出的判断：**「声称有类型检查和测试，但默认命令跑不通；构建能过不代表质量。」

### 第 5 步：抽样核心文件

它可能打开：

- `app/services/ai/agent/loop.py`（2,676 行）→ 看到 `run_agent_stream` 超长；
- `app/api/v1/questions.py`（4,027 行）、`rag.py`（3,153 行）→ 巨型路由；
- `front/workspace/index.vue`（6,512 行）、`QuestionBuilder.vue`（5,445 行）→ 巨型组件；
- `app/api/v1/carousel.py` → 看到 `class Carousel(Base)` 写在路由里。

**它得出的判断：**「有架构意识，但职责边界被巨型文件破坏。」

### 第 6 步：关键词搜索坏味道

它可能搜：

```
TODO|FIXME|HACK
console.log
print(
except:
except Exception:
: any
@ts-ignore
debugger
```

在 OpenStudy 会搜到：

- 后端 5 处裸 `except:`；57 处 `except Exception:`；116 个未使用导入；8 个未使用变量；6,473 条 ruff 默认告警；
- 前端约 1,379～1,958 个 `any`；`console.log` 已从 129～155 处降到 56 处；466 处内联 style；
- 0 个 TODO（这点反而是加分）。

**它得出的判断：**「代码里存在明显技术债，且有调试残留。」

### 第 7 步：看测试与版本

- `tests/` 有 100+ 文件，但大部分是 `_probe_*` / `e2e_*` 脚本；真正的 `test_*.py` 约 28 个；
- 没有 `pytest.ini`、没有覆盖率；
- `VERSION` 与 `pyproject` 是 0.7.1，README/package 是 0.8.0；
- `doc/代码质量提升实施方案.md` 描述的是「还没有 pytest」的旧基线。

**它得出的判断：**「测试资产有，但工程化不足；版本管理不严谨。」

### 第 8 步：搜死代码与调用链

它会跑/搜索：

```
rg "utils/generator|PageWithFilter|StudyPrescriptionPanel" src
rg "float-btn|悬浮" src
rg "favorites\.py|notice_repo" app
```

在 OpenStudy 当前会看到：`utils/generator`、`PageWithFilter`、17 个旧组件已删除；`AiAssistant` 的 `.float-btn` 已删除；后端 `favorites.py`/`notice_repo.py` 已删除。它会把「文档说已清理、代码确有 diff」视为可信证据。

### 第 9 步：看口径一致性

它会拿文档中的承诺逐条对照代码：

- 「没有悬浮助手」→ grep `float-btn` 是否为 0；
- 「笔记导入资料夹」→ 是否有 `note_kb_link` 表/服务/API/Agent 工具/前端入口；
- 「建议不是任务」→ `StudyAdvice` 是否含 `tasks/days/status/done`，旧 `StudyPrescriptionPanel` 是否已删；
- 「图谱能用」→ 是否有真实数据/真实边，而不是只有截图。

这是 LLM 评审最容易被说服、也最容易发现反例的一步。

### 第 10 步：看 AI 工具使用留痕与验收证据

它会找：

- `doc/dev-process/` 日志、session、memory；
- `quality-report.md` 中 pytest/ruff/lint/build/type-check 的真实输出；
- commit 记录是否与文档结论对得上（如 `ca5cf66`、`b91d493`、`a0ee935`）。

**它得出的判断：**「过程可追溯、验收有数字，但 type-check 仍有公开债务。」

---

## 3. 当前 16 项检查表（自评）

| # | 检查信号 | 当前状态 | 会被扣分的证据 | 最小修复动作 | 预期收益 |
|---:|---|---|---|---|---|
| 1 | 仓库结构 | ✅ 清晰 | — | 保持 | 免扣 |
| 2 | README/架构文档 | 🟡 丰富但过时 | 前端 README 写 Spring Boot 3；README 32 模块/20+ 工具与实际不符 | 统一 README 数据、加 `ARCHITECTURE.md` | 高 |
| 3 | lint/format | ✅ P0 已配置 | ruff.toml / eslint.config.js / .prettierrc.json 已加；lint 0 errors/3,214 warnings | P1 按规则清 warning | 极高 |
| 4 | type-check | 🟡 工具已修复，存量 2,993 条错误 | TS 已锁 5.3.3、Node heap 8GB；不再崩溃，但类型错误需 P1 批处理 | 按 `request.ts`/全局类型/文件分批收紧 | 极高 |
| 5 | test 可跑 + CI | ✅ 本地 99 passed；CI 已补 pytest step | `pytest.ini` + `asyncio_mode=auto`；CI 未在 runner 实跑 | 跑一次 GitHub Actions 并截图 | 高 |
| 6 | 异常处理 | ✅ P0 已清零裸 except | `auth.py/ai.py/notes.py/notice_front.py` 已改 `except Exception` + loguru | 保持 | 高 |
| 7 | 类型纪律 | 🟡 strict 开但 any 多 | 约 1,379～1,958 处 any | ESLint `no-explicit-any: warn` + `noUnusedLocals` | 中 |
| 8 | 死代码 | ✅ P0 已删第一批 | 17 孤儿组件、generator 1,340 行、旧首页/dictation/chats、AiAssistant 悬浮残留、25 个 `.bak` 已删；`rg "float-btn"` 0 | 保留清理台账；P1 继续扫尾 | 高 |
| 9 | 调试残留 | 🟡 全前端剩 56 处 console.log（Top3 已清） | `QuestionBuilder` 25 / `PracticeComponent` 14 / `CommentModal` 15 已删 | 继续清剩余 14 个文件；`no-console:warn` | 中 |
| 10 | 重复代码 | 🟡 OCR 双实现、Agent 双循环；分页已收口 | `api/v1` 分页模板清零 | 提 helper；写常量一致性测试 | 中 |
| 11 | 分层 | 🟡 P1 已迁出 4 个 ORM 模型 | `app/models/{carousel,chat_message,leave_message,sensitive_word}.py` | 补 alembic migration | 高 |
| 12 | commit 规范 | ✅ feat/fix/perf/docs 规整 | — | 保持 | 免扣 |
| 13 | 版本一致性 | ✅ P0 已统一 | VERSION / pyproject / package.json / main.py 全部 0.8.0 | 保持单一版本源 | 高（2 分钟） |
| 14 | 可运行证据 | ✅ pytest 收集通过、CI 在、compose 在 | CI 前端 job 会红 | 修 #4 后跑一次全绿 CI | 高 |
| 15 | 仓库卫生 | 🟡 P0 清了一批，仍有既有未跟踪项 | `300`/audit/type-errors/ts_errors/25 `.bak` 已删；`_scratch*/` 与 `doc/competition/码道架构图/` 已 ignore | 继续清 `doc/` 以外的历史垃圾 | 高 |
| 16 | 功能口径一致性 | ✅ P0 已统一（文档 + 代码） | 悬浮助手残留已清；旧学习处方组件删除；文档统一 v2.0 口径 | 保持 | 极高 |

**模拟评分（仅按本项 20 分制）：**

- **当前**：约 11～12 / 20（有测试/文档/架构，但门禁缺失、type-check 崩、死代码多）。
- **完成 P0（1～2 天）**：约 15～16 / 20（门禁齐全、版本一致、仓库干净、无裸 except）。
- **完成 P0+P1（1～2 周）**：约 17～18 / 20（测试进 CI、lint 基线、核心债务有台账）。
- 不要追求 20/20；LLM 评审对「有已知债务但可解释、有计划」的容忍度，远高于「自称完美但一搜全是洞」。

---

## 4. 最划算的 6 个「评审信号」动作（1～2 天）

### 动作 1：让 `npm run type-check` 真的能跑

LLM 评审很可能会试这条命令。修法：

```bash
cd openstudy-vue3-ts
npm install -D vue-tsc@^2.1 typescript@~5.3.3
npm run type-check
# 期望 exit 0
```

或者若坚持 TS 5.9：

```bash
npm install -D vue-tsc@^2.1
```

验收：`npm run type-check` exit 0，`npm run build:prod` 仍 exit 0。

> 注意：`vue-tsc@1.8.27` 不支持 TS 5.9 内部结构，这不是「配置问题」，是版本不兼容。

### 动作 2：让 `pytest` 默认就能跑

新建 `openstudy-fastapi/pytest.ini`：

```ini
[pytest]
testpaths = tests
pythonpath = .
addopts = -q --strict-markers
norecursedirs = .venv __pycache__ data _scratch*
```

新建 `openstudy-fastapi/tests/conftest.py`（如已有则合并）：

```python
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
```

删除/移出 `test_notice.py`（引用不存在的 `async_session`）；把 `_scratch/` 下临时测试移入 `tests/_scratch_archive/` 或删除。

验收：`pytest`（不带参数）102 passed，exit 0；CI 加：

```yaml
- name: 后端单元测试
  working-directory: openstudy-fastapi
  run: pytest tests -q
```

### 动作 3：给后端加 ruff 配置（先窄后宽）

`openstudy-fastapi/ruff.toml`：

```toml
target-version = "py311"
line-length = 120

exclude = [".venv", "__pycache__", "data", "htmlcov", "_scratch*"]

[lint]
select = ["E9", "F63", "F7", "F82", "F401", "F841", "E722"]
ignore = ["E501", "E402", "B008", "B904"]

[lint.per-file-ignores]
"tests/**" = ["F401", "F841", "E722"]
"test_*.py" = ["F401", "F841", "E722"]
```

先让 `ruff check app` 的 `E9/F63/F7/F82` 清零；F401/F841/E722 逐文件清。不要一上来开 UP/BLE/S110，会报 6,000+ 条，自己把自己吓退。

### 动作 4：修 5 处裸 `except:`

| 文件:行 |
|---|
| `app/api/v1/auth.py:101` |
| `app/api/v1/ai.py:405` |
| `app/api/v1/notes.py:1103` |
| `app/api/v1/notes.py:1138` |
| `app/api/v1/notice_front.py:68` |

改法：

```python
except Exception as e:  # noqa: BLE001 - 这里必须兜底，失败只影响当前响应
    logger.exception("[module] ...: {}", e)
```

每处加一句「为什么可降级」，不要只写 `pass`。

### 动作 5：删死代码，并在 commit 里说明依据

一次性删除：

- `src/utils/generator/*`（约 1,340 行，0 引用）；
- `src/components/PageWithFilter/`；
- 17 个零引用 Vue 组件/页面；
- `views/index.vue` 旧首页、`views/dictation` 旧听写链路、`messages/chats.vue`；
- `AiAssistant/index.vue:511-580` 悬浮按钮拖拽逻辑、`:1379-1431` `.float-btn`/`.assistant-entry` 死样式、`FrontSidebar:859-868` 死样式；
- `test_notice.py`、`test_ds_free.py`、`favorites.py`、`notice_repo.py`、`check_images.py`、`check_notice.py`；
- `type-errors.txt`、`ts_errors.txt`、`300`、`audit_ws_summary.json`、25 个 `.bak`。

**Commit message 示例：**

```
chore: remove dead code and stale debug artifacts

- remove 17 unreferenced Vue components/pages (~7.5k lines)
- remove legacy dictation/chats/old homepage routes (~3.4k lines)
- remove dead floating-assistant drag logic and .float-btn CSS (AiAssistant)
- remove stale backend scripts (test_notice/test_ds_free/favorites/notice_repo)
- remove tracked build error logs, 25 backup files and root temp files
- evidence: full-repo grep and router/import checks; no production references
```

### 动作 6：统一版本号

```diff
- VERSION: 0.7.1
+ VERSION: 0.8.0

- pyproject.toml: version = "0.7.1"
+ pyproject.toml: version = "0.8.0"
```

如果本轮 48 个提交算一个未发布版本，建议直接升 `0.9.0`，并同步 README/package/main。**不要三处不一致。**

---

## 5. 评审友好的「证据层」怎么建

LLM 评审喜欢**能被 grep/打开/引用**的文件。建议在 `doc/功能迭代与代码质量/` 下放：

| 文件 | 作用 |
|---|---|
| `OpenStudy-系统完整介绍与功能架构梳理.md` | 系统/模块/架构全貌 |
| `OpenStudy-代码质量审计与无用代码清理清单.md` | 死代码/质量债务/清理路线 |
| `LLM技术实现质量20%审查应对手册.md` | 本文件，回答评审方法论 |
| `README.md` | 目录索引 + 30 秒证据地图 |
| `quality-report.md`（建议新增） | 每次发版前跑 `pytest`/`ruff`/`type-check`/`build` 的真实输出摘要 |
| `dead-code-ledger.md`（建议新增） | 删除清单：文件、行数、引用证据、删除 commit |
| `ARCHITECTURE.md`（建议放仓库根） | 一页架构图 + 分层规则 + 数据流 |

### 5.1 建议给 README 加一节（评审第一眼）

```markdown
## 质量与工程实践

- 后端：`ruff check app --select E9,F63,F7,F82`（配置见 `openstudy-fastapi/ruff.toml`），`pytest tests`（99 个纯函数/服务测试通过，不依赖真实 LLM）；`npm run lint`（0 errors/3,214 warnings 基线）
- 前端：`npm run type-check`、`npm run build:prod`
- CI：`.github/workflows/ci.yml`（compileall + import + pytest + type-check + build + 仓库卫生）
- 架构：见 `ARCHITECTURE.md`；模块地图见 `doc/功能迭代与代码质量/OpenStudy-系统完整介绍与功能架构梳理.md`
- 质量报告：见 `doc/功能迭代与代码质量/quality-report.md`
- 开发过程留痕：见 `doc/dev-process/`（5 天日志 / 6 份会话 / 91 份 memory / 3,214 次工具调用 / 50 次提交）
```

> 关键不是「写一句质量很高」，而是给出**可执行命令 + 可打开文件 + 可复核数字**。

### 5.2 建议给「工具使用规范」留证据

如果评审的「工具使用」指 AI 编码工具，不要把证据藏着：

- `doc/dev-process/logs/`：5 天、10.9 MB 日志；
- `doc/dev-process/sessions/`：6 份完整 AI 分析会话；
- `doc/dev-process/memory/`：91 份决策/踩坑笔记；
- `doc/dev-process/codebase/index-report.md`：代码库索引记录；
- README `:458-472` 已有汇总：3,214 次工具调用、50 次提交、186 个文件改写，会话 ID/时间戳/工具调用/提交记录可交叉核对。

**应对话术：**

> 「我们的智能体核心三块（Agent 工具循环、工具链、RAG）使用华为云码道 CodeArts 开发，全过程留痕；`doc/dev-process/` 有 5 天日志、6 份会话、91 份 memory，工具调用次数、会话 ID、时间戳和 50 个 commit 可交叉核对。这不是口头声明，而是可复核的过程证据。」

---

## 6. 答辩/评审常见问题与回答

### Q1：为什么没有 lint / 测试门禁？

**不要回答「我们代码质量很高不需要」。** 正确回答：

> 「之前是快速迭代，工程门禁确实是短板。P0 已经把 `ruff.toml`、ESLint/Prettier、`pytest.ini` 和 CI 的 pytest step 补上：`pytest tests` 实测 99 passed，`ruff check --select E9,F63,F7,F82` 通过，`npm run lint` 是 0 errors/3,214 warnings 的 warn-only 基线。目标不是一次清掉所有存量，而是让新代码不再恶化、存量按 P1/P2 清单递减。」

### Q2：为什么 `questions.py` / `workspace/index.vue` 这么大？

> 「这两个文件是各自域的编排入口：`questions.py` 承载 70 个题库/题目端点，`workspace/index.vue` 承载资料空间的列表/书架/画廊/百科四个视图。它们确实超过合理体量，已在 P2 拆分计划里：先抽 `pagination.py` 和查询 helper，再按视图/子域拆组件；每一步有测试或构建保护。我们不把『大』说成『好』，但它有明确拆分路径。」

### Q3：`VERSION` 为什么和 README 不一致？

> 「这是版本管理疏漏：VERSION 和 pyproject 停留在 0.7.1，README/package/main 已是 0.8.0。P0 第一条就是统一版本源；后续由构建/发布脚本读取单一 VERSION，不再手写多处。」

### Q4：测试是不是只是摆设？

> 「不是。P0 后 `pytest tests` 是 99 passed、9 秒、不依赖真实 LLM；`test_wiki_service.py`、`test_study_map_service.py` 等覆盖纯函数/服务边界。原来的问题是测试没有进 CI、没有 pytest.ini，裸 pytest 会被根目录 `test_notice.py` 和 `_scratch` 干扰——这两处已清理，CI 也加了 pytest step。」

### Q5：死代码为什么这么多？是不是没人维护？

> 「部分是 RuoYi 脚手架和快速迭代的旧入口：`utils/generator` 约 1,340 行、17 个旧 Vue 组件、旧首页/听写/私信链路、`AiAssistant` 悬浮按钮残留约 100 行。P0 已按全仓引用核查删掉这批确定可删项（`build:prod` exit 0、`rg "float-btn"` 0）；需要查 DB 菜单的后台动态页列在 P1 待确认，不会盲删。」

### Q6：工具使用规范怎么证明？

> 「两条线：一是工程工具链，P0 后 `npm run type-check`、`pytest tests -q`、`ruff check`、`npm run build:prod` 全部可复跑；二是 AI 编码工具，`doc/dev-process/` 里的 5 天日志、6 份会话、91 份 memory、3,214 次工具调用和 50 个 commit 可交叉核对。前者证明『现在的代码有门禁』，后者证明『开发过程可追溯』。」

### Q7：你们说「一切皆对话」，但很多模块没有工具？

> 「对，当前是核心资料/题库/笔记域双向闭环、外围域还有孤岛。29 个工具覆盖题库/笔记/资料/英语/统计/百科；资料诊疗室、智能报告、题库关联、知识库分享、系统管理还没有工具。我们按 L0～L4 分级评估过：我的资料、题库、错题是 L4；笔记、知识百科是 L3；资料诊疗室是 L1（只能指路）；知识库分享、后台是 L0。我们已经在路线图里分了四阶段：先补已有闭环的确认/回滚/角色白名单/页面上下文，再补资料诊疗室和知识库分享，最后做统一的 Capability Manifest 和覆盖测试。我们不把『有对话页』等同于『一切皆对话』。」

### Q8：你们的智能图谱是不是摆设？能用吗？

> 「不是摆设，但**能用不等于好用**。本地验证库有 109 个知识百科页、241 条页面链接、704 个实体、745 条关系；孤儿关系 0、重名 0，实体 682/704 带 doc_ids、638/704 带 chunk_ids；`get_wiki_graph` 对 kb 640/604 实测 44～55 个节点、65～142 条边、0.03～0.45 秒。主题页→图谱→点节点→生成建议这条链路是真实的，建议来自真实 trace，没有假边。
> 但离『好用』还差五点：① 前端画布根本没渲染六类统一图——`KnowledgeWikiPanel.vue:2008` 用的是 `getWikiGraph`（page-only），`getStudyMap` 只在 `:1856` 列来源时用过一次，建议 trace 里的非 topic 步骤会被 `adviceTraceLines` 静默丢弃；② 748 道题只有 6 条 `question_source` 锚点（且 chunk_id 全 NULL），kb604 默认图只显示 1/6 个题库，`noQuestionSource` 恒真；③ 笔记节点恒 0（34 条有效笔记全未进图，唯一 note 引用指向已删文档 664）；④ 23 个 `source:bank` 页 `source_doc_ids/source_refs` 全空、正文仅 32–38 字符；⑤ 边 ID 用 `e:{kind}:{len(edges)+1}` 生成，跨请求不稳定，建议 evidence 会漂移。所以评级是『**能用 6/10**，主题页-建议链路局部好用，实体图/统一图/多来源接入还没产品化』。」

### Q9：既然没有悬浮助手，为什么代码里还有 `.float-btn`？

> 「对，UI 已经没有悬浮助手了：入口在侧边栏左上角品牌行的 `assistant-entry`，点击打开右侧 `AiAssistant` 抽屉；收起态只保留展开按钮。代码里 `AiAssistant/index.vue:511-580` 的拖拽逻辑和 `:1402-1431` 的 `.float-btn { position: fixed; ... }` 是历史残留，属于我们本轮 P0 要清理的无用代码——这也正好说明我们的审计不是只写文档，而是真的在对照代码找残留。清理验收标准之一就是全仓 `rg "float-btn"` 0 命中。」

### Q10：笔记能导入资料夹吗？

> 「**暂时还没做。** 没有 `note_kb_link` 表、没有导入/解绑/知识点预览端点、没有 Agent `note_import` 工具；现有只是『笔记↔题库/题目』关联，以及『笔记→知识百科主题页』的通用 `ContentReference` 旁路。前端 `notes/detail.vue:243` 也明确写着『导入知识库功能已移除』。我们把它列进 P2：新增 `note_kb_link` 表 + 4 端点 + service + Agent 工具 + 前端入口，复用现成的 `extract_entities_from_text` / `sync_text_source`，不复制笔记正文。题库导入资料夹已经做了，两者不要混为一谈。」

### Q11：智能报告是不是每次都调用大模型？有没有历史？

> 「不一定。默认 `useLlm=true` 会尝试调用；`useLlm=false` 或模型失败/超时/返回非法 JSON 时，会回退到基于体检规则的模板报告，并用 `degraded.llmFallback=true` 明确标注『未调用模型』。报告**不写库、没有历史版本、刷新会重新生成**——这是当前已知缺口（B20）。另外有一处边界要诚实：如果模型返回合法 JSON 但零个有效改进项，我们用模板补齐时仍标了 `llmFallback=false`，这个标志需要修（`document_smart_report_service.py:158-159`）。」

### Q12：`npm run type-check` 为什么还有几千条错误？

> 「先说结论：**工具已修复，但类型债务未清零**。旧问题是 `vue-tsc 1.8.27 + TypeScript 5.9.3` 直接崩溃；现在锁 TypeScript 5.3.3、Node heap 8GB，命令能完整跑完，暴露的是真实存量错误（当前 **2,993 条**，初始 3,218）。主要集中在 RuoYi 后台页（system/monitor/questionMarked/questionError 等）、历史组件的 `ref({})` 推断和 `catch (error)` 的 unknown 类型；我们不会把『能跑』说成『已通过』，P1 按文件批处理，下一步目标先降到 2,000 以下。」

### Q13：笔记导入资料夹做到什么程度？

> 「**已完成 P2 首条完整闭环**：`note_kb_link` 表 / service / 4 个 API（列表、关联、取消关联、知识点预览）/ `source_graph_state_service` 来源集 / Agent `note_kb_link` 工具 / 笔记详情『加入资料夹』入口均已接通；关联后后台用 `sync_text_source` 抽实体与关系。它不复制笔记正文，只建立逻辑引用。前端与 Agent 的 29 个工具标签也已覆盖。」

### Q14：你们图谱为什么有四套服务，是不是重复建设？

> 「历史上确实叠了四层：`knowledge_map_service` 旧页面层级图、`knowledge_graph_service` 实体图、`study_graph_service` 旧学习图、`study_map_service` 六类统一图。当前用户主路径是 `wiki_service.get_wiki_graph`（主题页图）+ `study_map_service`（建议 trace）；另外两套是历史兼容/内部能力。我们不把四套说成优点：P2 会统一 `GraphNode/GraphEdge` 契约、补实体图入口或明确下线、把边 ID 改为内容派生，再决定是否保留旧端点。」

---

## 7. 「不要做」清单（LLM 评审最反感）

| 不要做 | 原因 |
|---|---|
| 说「代码质量很高」但没有数字/命令 | 空泛自我评价反而扣分 |
| 为了让覆盖率好看写无意义断言 | 评审能看出 `assert True` / 空壳测试 |
| 隐藏死代码、把 `_scratch` 留在根目录 | 一搜就穿帮 |
| 只改 README 不改代码 | 评审会对照文件树/配置 |
| 把 `vue-tsc` 错误说成「环境问题」 | 锁版本可复现，是兼容性问题 |
| 把 `agentDsFree.ts` 说成重复封装 | 它是设计上的第二传输通道，误判显得没读代码 |
| 把 `learning_chart.py` 说成未注册工具 | 它是辅助模块，误判显得没读代码 |
| 把确认卡说成「只在前端」 | 当前 SSE 有服务端 `asyncio.Event`、非流式有 HMAC 票据，历史漏洞已修 |
| 把 `study_plan` 说成「只读、无计划表」 | 代码会落 `study_plan_snapshot`，注释与实现有矛盾，需先修口径 |

---

## 8. 两周执行清单（按天）

| 天 | 动作 | 产出/验收 |
|---|---|---|
| D1 上午 | 统一版本号；删 `300`/`audit_ws_summary.json`/`type-errors.txt`/`ts_errors.txt`；补 `.gitignore` | `git status` 干净；VERSION 全 0.8.0 |
| D1 下午 | 修 `vue-tsc`/TS 版本；删一个锁文件；跑 type-check | `npm run type-check` exit 0 |
| D2 | 加 `pytest.ini` + `conftest.py`；删 `test_notice.py`；CI 加 pytest job | `pytest` 102 passed；CI 绿 |
| D3 | 加 `ruff.toml`；5 处裸 except 清零；`ruff check app --select E9,F63,F7,F82` 通过 | ruff 基线报告 |
| D4 | 删 17 个孤儿组件 + `utils/generator` + 旧首页/dictation/chats + `AiAssistant` 悬浮按钮残留 | commit + 行数统计；`rg "float-btn"` 0 命中 |
| D5 | 加 ESLint/Prettier（warn 模式）；清 QuestionBuilder/CommentModal/PracticeComponent 的 console.log | `npm run lint` 可跑 |
| D6-D7 | 提取 `pagination.py`；4 个 ORM 模型迁出 API | 测试/构建通过 |
| D8-D10 | 补 `TOOL_LABELS`/`ACTION_LABELS`；4 个写工具确认/回退；7 个工具角色白名单；补资料诊疗室只读工具 | Agent 工具矩阵检查 |
| D11-D14 | 加 `ARCHITECTURE.md`、`quality-report.md`、`dead-code-ledger.md`；README 质量节；图谱统一图接前端/边 ID 内容派生；跑一次完整 CI 截图 | 评审证据包 |

---

## 9. 一页速查（给答辩前 5 分钟看）

**评审会看：** 根目录配置 → README → scripts → type-check → pytest → 大文件 → 坏味道搜索 → 测试/版本 → 死代码 → AI 工具留痕。

**我们现在：** 功能强、Agent 主链路强、文档强；门禁弱、版本乱、死代码多、type-check 崩。

**P0 五个动作：**
1. 版本统一；
2. `vue-tsc` 修复；
3. `pytest.ini` + CI pytest；
4. `ruff.toml` + 5 处裸 except；
5. 删死代码 + 仓库卫生。

**答辩口径：**
> 「我们不是没有技术债，而是有清单、有优先级、有验收标准。P0 先让门禁可跑，P1 清结构性债务，P2 做拆分和类型化。所有结论都能在 `doc/功能迭代与代码质量/` 找到文件和命令证据。」

**最后一句：**
> **LLM 评审给高分的关键，不是「你说了什么」，而是「它一打开仓库能看到什么、一跑命令能得到什么」。**
