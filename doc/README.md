# OpenStudy 文档索引

> 这是 `doc/` 的唯一入口。评委/新同学先看本页，再按“想确认什么”跳转。
> 文档基线以本目录最新 `quality-report.md` 和 `OpenStudy-技术实现质量20%-P0-P2执行方案.md` 为准；历史审查报告只作快照。

## 30 秒证据地图

| 想确认 | 打开 | 一句话结论 |
|---|---|---|
| 架构与边界 | [ARCHITECTURE.md](../ARCHITECTURE.md) | Vue3/FastAPI/Postgres；Agent/RAG 主链路与已知债务 |
| 系统是什么、功能全貌 | [OpenStudy-系统完整介绍与功能架构梳理.md](功能迭代与代码质量/OpenStudy-系统完整介绍与功能架构梳理.md) | 信息来源处理系统，不是单一刷题站 |
| 功能在哪、由谁实现 | [feature-map.md](feature-map.md) | 15 个功能域 → 入口 → 后端 → 证据 |
| API 与数据模型 | [architecture/api-data-model.md](architecture/api-data-model.md) | 42 路由域、80 表、29 工具契约 |
| 测试策略 | [quality/test-strategy.md](quality/test-strategy.md) | 109 pytest 现状、分层目标与覆盖率路线 |
| 架构决策 | [adr/README.md](adr/README.md) | FastAPI/自研 Agent、PG/pgvector、图谱契约 |
| 技术实现质量如何 | [quality-report.md](功能迭代与代码质量/quality-report.md) | pytest/ruff/lint/build 可复跑；type-check 存量债务如实披露 |
| 20% 评分怎么整改 | [OpenStudy-技术实现质量20%-P0-P2执行方案.md](功能迭代与代码质量/OpenStudy-技术实现质量20%-P0-P2执行方案.md) | P0 证据/卫生 → P1 结构/文档 → P2 债务减量 |
| 死代码清理依据 | [OpenStudy-代码质量审计与无用代码清理清单.md](功能迭代与代码质量/OpenStudy-代码质量审计与无用代码清理清单.md) | 删除清单、引用核查、清理路线 |
| 闭环/P0/P1/P2 修复证据 | [闭环检查/00-汇总报告.md](闭环检查/00-汇总报告.md) | 多模块双视角复核与 evidence 目录 |
| 开发过程留痕 | [dev-process/README.md](dev-process/README.md) | 日志、会话、memory 与工具调用记录 |
| 部署与排障 | [deploy/SKILL.md](deploy/SKILL.md)、[deploy/TROUBLESHOOTING.md](deploy/TROUBLESHOOTING.md) | Docker / Linux / Windows / 公网访问 |

## 目录分层

```text
doc/
├── README.md                       # 本索引
├── 功能迭代与代码质量/              # 产品介绍、质量审计、质量报告、20% 方案
├── 闭环检查/                       # 模块闭环、P0/P1/P2 修复证据
├── dev-process/                    # AI 工具使用过程留痕（日志/会话/memory）
├── deploy/                         # 部署与排障
├── planning/                       # 规划、方案与实施记录（逐步转 ADR）
├── competition/                    # 竞赛材料（成品保留；预览/缓存不入库）
├── screenshots/                    # 界面截图（只保留 README 引用资产入库）
├── demo/                           # 演示数据与讲稿
├── internal/                       # 内部资料（默认不入库）
└── legacy/                         # 历史项目归档（逐步移出主仓）
```

## 文档权威顺序

1. **代码/命令实测结果**：`quality-report.md`、CI run；
2. **当前整改方案**：`OpenStudy-技术实现质量20%-P0-P2执行方案.md`；
3. **架构与功能事实**：`OpenStudy-系统完整介绍与功能架构梳理.md`；
4. 历史审查/方案：只作背景，若数字或口径冲突，以 1–2 为准。

## 维护规则

- 新增质量数字只能写入 `quality-report.md` 一处，其他文档引用链接，不复制第二份；
- 大型截图、临时导出、竞赛预览和本地素材不进入 Git；
- 本索引新增/重命名文档时同步更新根 `README.md` 的“文档”与“质量与工程证据”区；
- 历史文档不删除，移动到 `_archive/` 或 `legacy/` 并标注“历史快照”。
