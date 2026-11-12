# OpenStudy 死代码与仓库清理台账

> 基线：2026-11-12；配套审计：[OpenStudy-代码质量审计与无用代码清理清单.md](OpenStudy-代码质量审计与无用代码清理清单.md)
> 原则：先做全仓引用核查，再删除；无法确认是否被数据库菜单/外部入口引用的，不盲删。

## 1. 已清理（第一批，来自历史审计与 quality-report）

| 类别 | 范围 | 依据 | 结果 |
|---|---|---|---:|
| 前端孤儿组件/页面 | 17 个零引用 Vue 组件/页面 | 全仓 import/route grep + 构建 | 约 −7.5k 行 |
| 旧工具 | `src/utils/generator/*` | 0 import | 约 −1,340 行 |
| 旧入口 | `views/index.vue` 旧首页、旧 dictation、`messages/chats.vue` | 路由/菜单核查 | 约 −3.4k 行 |
| 悬浮助手残留 | `AiAssistant` 拖拽逻辑、`.float-btn` / `.assistant-entry` 死样式 | `rg "float-btn"` = 0 | 约 −100 行 |
| 后端旧脚本 | `test_notice.py`、`test_ds_free.py`、`favorites.py`、`notice_repo.py`、`check_images.py`、`check_notice.py` | 0 引用 | 已删 |
| 错误日志/备份 | `300`、`audit_ws_summary.json`、`type-errors.txt`、`ts_errors.txt`、25 个 `.bak` | 仓库卫生审计 | 已删 |
| 合计 | — | `git diff --stat` | 约 −14,124 行 |

## 2. 已从 Git 索引脱管（本地保留）

| 路径 | 文件数/大小 | 原因 | 规则 |
|---|---:|---|---|
| `openstudy-fastapi/tests/_evidence/` | 74 文件 / 1.4 MB | 运行时输出，非产品资产 | `.gitignore` 已含 |
| `openstudy-fastapi/tests/_ui_evidence/` | 7 文件 / 0.77 MB | UI 运行截图 | `.gitignore` 已含 |
| `openstudy-fastapi/tests/.e2e_agent_mem_baseline` | 1 文件 | 一次性基线快照 | 已加入规则 |
| `doc/competition/码道架构图/` | 23 文件 / 2.27 MB | 竞赛展示可再生产物 | `.gitignore` 已含 |
| `doc/competition/_preview/` | 10 PNG | 逐页预览，可由脚本重生成 | 新加入规则 |
| `startup-scripts/package-lock.json` | 1 文件 | 无对应 package.json 的孤儿锁 | 新加入规则 |
| `openstudy-vue3-ts/tests/.tmp_p_none.txt`、`.tmp_p_norm.txt`、`_served.js` | 3 文件 | 临时探测/本地服务产物 | 新加入规则 |

> 脱管命令必须是 `git rm --cached`，不是 `rm`；本地文件保留。

## 3. 仍待 P1/P2 决策

| 项 | 风险 | 建议 |
|---|---|---|
| `doc/screenshots/` 约 113 PNG / 27.8 MB | README 只引用部分截图，其余是过程证据 | 只跟踪 README 引用资产，其余放 Release/本地 |
| `doc/闭环检查/` 162 文件 / 16 MB | 含大量证据截图 | Markdown 保留，图片外置/Release |
| `doc/competition/*.pdf` / `*.pptx` | 成品可能用于提交 | 保留成品，忽略预览/缓存 |
| `openstudy-fastapi/tests/` 平铺 | 31 个 `test_*.py` 无分层 | P1 拆 `unit/integration/contract` |
| `alembic.ini` 指向不存在的 `alembic/` | 迁移不可回滚 | P1 补版本化迁移 |
| 根 `.env`（299B，未跟踪） | 可能误提交 | 确认不含真实密钥，仅保留 `.env.example` 入库 |
| 双锁 `package-lock.json` + `pnpm-lock.yaml` | 依赖漂移 | 保留一个并让 CI 使用 `npm ci` |

## 4. 验收命令

```powershell
git status --short
git ls-files | Select-String -Pattern '_evidence/|_ui_evidence/|码道架构图|_preview/|\.tmp_|_served\.js'
rg "float-btn|utils/generator|PageWithFilter|StudyPrescriptionPanel|favorites.py|notice_repo" .
```

期望：`git status` 只显示明确的本地用户文件；上述 `git ls-files` 与 `rg` 均为 0 命中（历史文档/本台账自身除外）。
