# OpenStudy 质量证据目录

> 唯一原则：质量数字只维护一份；本目录负责索引，不复制第二套数字。

| 想确认 | 文件 |
|---|---|
| 当前质量验收、pytest/ruff/lint/build/type-check 结果 | [quality-report.md](../功能迭代与代码质量/quality-report.md) |
| 测试策略、分层与覆盖率路线 | [test-strategy.md](test-strategy.md) |
| 已删除/已脱管/待决策的死代码台账 | [dead-code-ledger.md](../功能迭代与代码质量/dead-code-ledger.md) |
| 质量整改 P0–P2 方案 | [执行方案](../功能迭代与代码质量/OpenStudy-技术实现质量20%-P0-P2执行方案.md) |
| 模块闭环/P0 修复证据 | [00-汇总报告.md](../闭环检查/00-汇总报告.md) |

## 当前边界

- `npm run type-check` 目前 **exit 2、1,808 条存量错误**，是报告型，不是绿门禁；
- `npm run lint` 当前 **0 errors / 3,506 warnings**，是 warn-only 基线；
- coverage 19% 为历史基线，复跑需先修 coverage 写入 INTERNALERROR；
- 不把上述债务写成“已清零”，也不把 `build:prod` 通过等同于类型检查通过。
