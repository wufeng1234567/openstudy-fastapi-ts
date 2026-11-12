# 功能迭代与代码质量 · 文档索引

> 目录定位：OpenStudy 当前迭代的功能盘点、信息来源处理叙事、架构梳理、代码质量审计与 LLM 评审应对材料。
> 审计基线：`main @ 14c82dd`（2026-11-09）
> 文档版本：v2.0（2026-11-09 修订）
> 说明：本目录是文档资产，不参与后端/前端运行时构建。

## 文档清单

| 文档 | 用途 | 适合谁看 |
|---|---|---|
| [OpenStudy-系统完整介绍与功能架构梳理.md](OpenStudy-系统完整介绍与功能架构梳理.md) | 系统全貌：用户信息来源处理定位、当前迭代、15 个功能域、资料诊疗/智能报告、智能图谱可用性、模块交互、技术架构、一切皆对话评估 | 产品/答辩/新同学 |
| [OpenStudy-代码质量审计与无用代码清理清单.md](OpenStudy-代码质量审计与无用代码清理清单.md) | 质量基线、死代码清单、后端/前端问题、图谱四套服务冗余、测试现状、P0/P1/P2 清理路线 | 开发/技术负责人 |
| [LLM技术实现质量20%审查应对手册.md](LLM技术实现质量20%审查应对手册.md) | 同行 LLM 会怎么检查、当前评分、6 个高杠杆动作、资料域/图谱/口径一致性答辩问答 | 答辩/评审准备 |
| [quality-report.md](quality-report.md) | 可复核的质量验收证据：pytest/ruff/lint/build/type-check 真实输出与债务边界 | 答辩/技术负责人 |
| [code-quality-review.md](code-quality-review.md) | 代码质量文档的对内审查结论、已修问题与不可夸大的债务边界 | 开发/答辩 |
| [llm-handbook-review.md](llm-handbook-review.md) | LLM 答辩手册的目标任务完成审查、数字一致性与使用边界 | 答辩/评审 |
| [ruoyi-cleanup-report.md](ruoyi-cleanup-report.md) | RuoYi-Vue3 历史组件删除、品牌资产替换与保留边界 | 开发/重构 |
| [OpenStudy-技术实现质量20%-P0-P2执行方案.md](OpenStudy-技术实现质量20%-P0-P2执行方案.md) | 比赛 20% 评分对应的 P0/P1/P2 整改方案、完整工程结构与证据地图 | 答辩/技术负责人 |

## 30 秒结论

- **产品**：OpenStudy 是面向「用户」的信息来源处理系统，不是只服务学生/老师的刷题网站。网页/图片/文档/比赛通知/学习报告/事件记录 → 我的资料 → 解析 → 资料体检（四维）→ 智能报告（更新目标/优势/改进项/下一步）→ 实体/关系图谱 → 规划建议。
- **智能体**：对话是默认首页；OpenStudy 助手入口在**侧边栏左上角品牌行**（右侧抽屉，无悬浮球）；29 个工具；SSE/确认/回滚/记忆/子代理主链路完整；核心资料/题库/笔记域双向闭环，资料诊疗室/智能报告/题库关联/知识库分享/后台仍是孤岛。
- **智能图谱**：评级「能用 6/10」。真实数据、真实边、百毫秒级响应；2026-11-10 已把知识图谱主画布接入统一六类节点（知识主题 + 题库/资料/网页/笔记/图片来源），移除独立「六类图」入口，补主题页来源合并与跨组边；但题源锚点仍少、大图懒加载和页面合并 redirect 待完善，不能称「好用」。
- **笔记导入资料夹**：后端 `note_kb_link` 表/服务/4 端点 + Agent `note_kb_link` 工具 + 资料夹「导入笔记」入口已完成（P2）。题库导入资料夹已经做了（逻辑引用，不复制题目）。
- **P1 第一批**：工具标签补齐 29/29、`api/v1` 分页样板已全部迁移到 helper、4 个 ORM 模型从 API 层迁入 `app/models/`、5 个工具补角色白名单、覆盖率基线 19%、`console.log` 从 129～155 处降到 56 处；type-check 3,218→1,808（2026-11-12 复核）。
- **当前迭代**：0.8.0 之后的 48 个提交（2026-11-08～09）主题是「规划建议工作台 + 六类节点统一图谱 + 来源实体集增量更新 + 资料夹题库关联 + 资料智能报告」，README 的 0.8.0 段落已落后。
- **代码质量**：P0 第一批已执行——版本统一 0.8.0、pytest 配置（102 passed）、ruff 语法门禁通过、ESLint/Prettier 基线（0 errors/3,506 warnings，2026-11-12 复核）、25 个 `.bak` 与 17 个零引用 Vue 组件已删、`AiAssistant` 悬浮按钮残留已清（`rg "float-btn"` 0）、`npm run build:prod` exit 0。**type-check 工具已修复；P1 第一批修 `request.ts` 返回类型与全局组件属性后，存量错误从 3,218 降到 1,823，仍列 P1 首项**；CI 配置已补 pytest/ruff step，并已在 GitHub Actions runner 实跑成功（run `42630095384`，3 jobs 全绿；type-check 为报告型步骤）。
- **评审风险**：LLM 评审不会读完全部代码，它看「根目录配置 + README + 可执行命令 + 大文件/坏味道搜索 + 死代码/版本 + 口径一致性」。先把 P0 门禁接电，比继续加功能更划算。

## 建议阅读顺序

1. **先看** `OpenStudy-系统完整介绍与功能架构梳理.md` 第 0、1、2、3.5、3.7、4、6 章，建立「用户信息来源处理」全貌与智能图谱真实边界；
2. **再看** `OpenStudy-代码质量审计与无用代码清理清单.md` 第 3、4.6、5、8、10 章，明确该删什么、先修什么；
3. **答辩前** 看 `LLM技术实现质量20%审查应对手册.md` 第 2、3、6（Q1-Q11）、9 章，准备口径与证据。

## 关键数字（审计基线）

| 指标 | 数值 |
|---|---:|
| 后端 `app/` Python | 245 个（P0 清理后）/ 96,111 物理行（审计基线） |
| 前端 `src/` | 437 个文件 / 179,276 物理行（审计基线）；P0 清理后 `.vue` 276 → 254 |
| 已挂载路由模块 | 42 个 |
| ORM 表 | 80 张 |
| Agent 工具 | 29 个 |
| 后端 pytest 用例 | 109 个（2026-11-12 collect；`pytest tests` exit 0） |
| 本地验证库知识百科 | 109 页 / 241 链接 / 704 实体 / 745 关系 |
| 当前质量评分（本目录口径） | 5.5 / 10 |
| 智能图谱评级 | 6.0 / 10（能用，不算好用） |
| 完成 P0 后预期 | 7.0～7.5 / 10 |

## 证据与重跑

本目录三份文档的关键结论均可按以下命令复核（在仓库根 `D:\OpenStudy\apps\fastapi-v2`）：

```powershell
# 版本
Get-Content VERSION
Select-String -Path openstudy-fastapi/app/main.py -Pattern 'version="'
Select-String -Path openstudy-vue3-ts/package.json -Pattern '"version"'

# 后端测试
cd openstudy-fastapi
.\.venv\Scripts\python.exe -m pytest tests --collect-only -q
.\.venv\Scripts\python.exe -m pytest --collect-only -q
.\.venv\Scripts\python.exe -m ruff check app --statistics

# 前端类型检查/构建
cd ..\openstudy-vue3-ts
npm run type-check
npm run build:prod

# 死代码/悬浮残留检查
rg "float-btn" src
rg "utils/generator" src
rg "StudyPrescriptionPanel|StudyPackPanel|StudyPackDialog" src

# 仓库卫生
cd ..
git status --porcelain
```

> 注：文档中的行号以审计时 `main @ 58f12c7` 为准；后续代码改动可能使行号偏移，请用文件/函数名搜索定位。
