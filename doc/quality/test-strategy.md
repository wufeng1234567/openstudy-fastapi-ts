# OpenStudy 测试策略

> 基线：2026-11-12。原则：测试必须可复跑、能失败、有边界；不写 `assert True` 式空壳。

## 1. 当前基线

| 项目 | 命令 | 结果 |
|---|---|---|
| 后端收集 | `pytest tests --collect-only -q` | 109 tests collected |
| 后端执行 | `pytest tests -q` | exit 0 |
| 语法/未定义名 | `ruff check app --select E9,F63,F7,F82` | pass |
| 全量 ruff | `ruff check app --statistics` | 约 115 errors（107 F401 + 8 F841），待 P1 |
| 覆盖率 | `pytest tests --cov=app/services --cov-report=term-missing` | 历史值 19%，当前复跑需修 coverage 写入 INTERNALERROR |
| 前端 lint | `npm run lint` | 0 errors / 4,156 warnings |
| 前端构建 | `npm run build:prod` | exit 0 |
| 前端 type-check | `npm run type-check` | 历史参考：exit 2 / 1,080 error TS（不纳入门禁） |
| 前端单测 | `npm run test:unit` | 2 个 Node 测试、29 项断言通过（mindmap 15 + table 14），exit 0 |

## 2. 分层目标

```text
openstudy-fastapi/tests/
  unit/          # 纯函数、schema、service 边界
  integration/   # DB/Redis/API 集成
  contract/      # Agent 工具 schema、前后端 JSON 契约
openstudy-vue3-ts/tests/
  unit/          # Vitest：utils/composables
  e2e/           # Playwright：登录、资料上传、练习、Agent smoke
```

## 3. P1 最小落地

1. 先建立 `unit/`、`integration/`、`contract/` 目录约定，不强行搬完 109 个存量测试；
2. 新增前端 Vitest 配置与 3 个纯函数/composable 测试；
3. Playwright 只做 3 条 smoke：登录、资料空间打开、练习页打开；
4. CI 把 `npm run build:prod`、`pytest tests -q` 设为 blocking；type-check 继续显式报告型；
5. 覆盖率先报告，P2 再设 30% 阈值；当前前端已有 2 个纯函数/渲染测试脚本，继续补 Vitest。

## 4. 约束

- 不测试真实 LLM 输出文本；测试工具 schema、路由、状态转换和降级边界；
- 前端测试不依赖真实后端，使用 mock/fixture；
- 测试数据不提交到 Git（`doc/test-data` 只保留可公开小样本）；
- 失败必须定位到文件/命令，不接受“环境问题”式解释。
