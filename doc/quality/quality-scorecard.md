# 技术实现质量 20% 评分卡

> 用途：对照比赛评分项「工具使用是否规范、代码可读性与可维护性」做保守自评，不冒充官方评分。
> 基线：2026-11-12；证据以 [quality-report.md](../功能迭代与代码质量/quality-report.md) 第 0 节和 `.github/workflows/ci.yml` 为准。

## 1. 评分拆分

| 子项 | 分值 | 当前判断 | 主要证据 |
|---|---:|---|---|
| 工程工具链：lint / format / type-check / test / CI | 10 | **约 6.5 / 10** | `eslint.config.js`、`.prettierrc.json`、`pytest.ini`、`ruff.toml`、`ci.yml`、`scripts/verify-quality.bat` |
| 代码可读性与可维护性：目录、命名、分层、类型、重复、大文件、死代码 | 10 | **约 6 / 10** | `ARCHITECTURE.md`、`doc/feature-map.md`、`doc/engineering/frontend-refactor.md`、死代码台账 |
| 合计 | 20 | **保守约 12.5 / 20** | 不把 type-check 1,808 条、lint 3,506 warnings 写成已清零 |

## 2. 工具使用规范（10 分）

| 检查 | 状态 | 证据/说明 |
|---|---|---|
| lint 可跑 | ✅ 0 errors / 3,506 warnings（warn-only） | `npm run lint`；warning 是存量债务 |
| format 可跑 | ✅ Prettier 配置在 | `npm run format:check` |
| type-check 可跑 | 🟡 工具可跑，但 exit 2 / 1,808 errors | 不宣称通过；CI 为报告型 |
| 后端测试可跑 | ✅ 109 tests collected，`pytest` exit 0 | `pytest.ini`、`tests/conftest.py` |
| 前端测试可跑 | ✅ `npm run test:unit`，29 项断言 | mindmap 15 + latex table 14 |
| CI 存在 | ✅ 3 jobs；lint/test/build/hygiene/版本检查 | `.github/workflows/ci.yml` |
| CI 强门禁 | 🟡 type-check 非阻塞；后端 ruff 只跑语法子集 | 继续 P1 |
| 一条命令验证 | ✅ `scripts/verify-quality.bat` | 输出 type-check 错误数，不伪装 |
| Vue composable import 检查 | ✅ `scripts/check_composable_imports.py` | 248 个 Vue 文件扫描通过；防止 `useXxx` 未 import 的 setup 崩溃 |
| 依赖锁 | ✅ 前端唯一 `package-lock.json` + CI `npm ci`；后端 requirements 未锁 hash | P1 继续 |
| 密钥/垃圾检查 | ✅ CI 检查 `.env`、node_modules、生成物、硬编码密钥 | 已脱管历史生成物 |

## 3. 代码可读性与可维护性（10 分）

| 检查 | 状态 | 证据/说明 |
|---|---|---|
| 目录分层 | ✅ `views/components/composables/utils/styles` 已写入规范，workspace/Practice 已按此拆分 | `ARCHITECTURE.md`、`doc/engineering/frontend-refactor.md` |
| 架构文档 | ✅ `ARCHITECTURE.md` | 分层、主链路、已知边界 |
| 功能地图 | ✅ `doc/feature-map.md` | 15 功能域 → 入口 → 后端 |
| API/数据模型 | ✅ `doc/architecture/api-data-model.md` | 42 路由域、80 表概览 |
| 大文件 | 🟡 `QuestionBuilder.vue` 等仍超 1,000 行 | P2 拆分计划 |
| 死代码 | ✅ 第一批清理 + 台账 | `doc/功能迭代与代码质量/dead-code-ledger.md` |
| 重复实现 | 🟡 OCR/图谱服务仍有历史重复 | P2 收口 |
| 类型纪律 | 🟡 1,808 条 type errors、3,506 warnings | 公开债务 |
| 注释/文档一致性 | 🟡 历史文档已标注快照；仍需持续对齐 | 以 quality-report 为唯一数字源 |
| 可运行证据 | ✅ build/pytest/lint 可复跑；type-check 如实披露 | `quality-report.md` |

## 4. 下一步优先级

- **P0 剩余**：CI 真实跑一次新配置；后端 requirements hash/lock；type-check 报告与实际输出归档。
- **P1**：type-check 按文件下降；前端 Vitest/Playwright；后端测试分目录；`dead-code-ledger` 扩展到逐文件。
- **P2**：拆 `QuestionBuilder.vue`、`loop.py`、`questions.py`、`rag.py`；统一图谱服务；清 any/console/重复实现。

## 5. 一句话口径

> 我们有真实的测试/构建/CI 和清理台账，也有公开的 type-check、lint warning、大文件债务；不把“能跑”说成“全绿”，不把“有文档”说成“已高质量”。下一步按 P0→P1→P2 递减。
