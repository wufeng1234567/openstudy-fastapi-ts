# RuoYi-Vue3 历史包袱清理记录

> 执行日期：2026-11-09
> 范围：`openstudy-vue3-ts`，前端前身为 RuoYi-Vue3。
> 口径：先由 hy4free / MiniMax-M3.1-Flash 两个子代理只读探索，再由主代理核对引用、静态路由、`sys_menu` 动态菜单与 `main.ts` 全局注册后执行。

## 一、已删除的确认无用项

| 路径 | 原用途 | 引用核对 |
|---|---|---|
| `src/components/AgentToolPopover/index.vue` | 旧工具浮层 | 0 import，仅注释提及 |
| `src/components/BankCard/index.vue` | 旧题库卡片 | 0 import |
| `src/components/BankCardList/index.vue` + `BankFilterSidebar.vue` | 旧题库列表实现 | 0 import |
| `src/components/FilterSidebar/index.vue` | 旧筛选侧栏 | 0 import，已由 `CommonFilterSidebar` 取代 |
| `src/components/KnowledgeBaseDrawer/index.vue` | 旧知识库抽屉 | 0 import |
| `src/components/MyQuestion/QuestionEmpty.vue` | 空态占位 | 0 import |
| `src/components/MyQuestion/QuestionList.vue` | 旧题目列表 | 0 import |
| `src/components/MyQuestion/QuestionLoading.vue` | 空壳 loading | 0 import |
| `src/components/MyQuestion/QuestionFilterSidebar.vue` | 旧筛选侧栏 | 0 import |
| `src/components/PracticeComponent/PracticeResult.vue` | 旧练习结果页 | 0 import |
| `src/views/front/myQuestion/myFavoriteBank/index.vue` | 已合并的题库收藏旧页 | 路由仅 redirect，无引用 |
| `src/components/QuestionCardGrid/QuestionCardGrid.vue` | 旧题目卡片网格 | 上一轮已确认 0 import |
| `src/views/courses/courses/index.vue` | 旧课程 CRUD 页 | 0 import、静态路由、`sys_menu` 均无 |
| `src/views/noteImage/noteImage/index.vue` | 旧笔记图片页 | 同上 |
| `src/views/ocr/ocr/index.vue` | 旧 OCR 后台页 | 同上 |
| `src/views/system/dept/index.vue` | 旧部门管理页 | 同上 |
| 对应 `src/api/courses` / `src/api/noteImage` / `src/api/ocr` | 旧页面 API 包装 | 0 外部 import |

> 说明：`monitor/ratelimit` 在本机 `sys_menu` 仍有「AI 限流」菜单，**保留**；`monitor/druid` 等 seed 菜单页也保留，避免后台菜单白屏。

## 二、RuoYi 品牌清理

- 删除 `src/assets/logo/logo.png`（若依书本+电路孤儿 Logo）
- 删除 `src/assets/logo/openstudy.png`（若依图形叠加 OpenStudy，已由 `OsLogo` 黑底白 O 组件替代）
- `src/utils/ruoyi.ts` → `src/utils/legacy.ts`，14 处 import 同步更新
- `src/assets/styles/ruoyi.scss` → `src/assets/styles/legacy.scss`，`index.scss` 同步更新
- `package.json` repository 改为 OpenStudy 仓库
- README/SstyleREADME/环境注释/压缩插件注释/monitor job 提示中的 RuoYi 文案清理
- `Copyright (c) 2019/2022 ruoyi` 头改为 OpenStudy
- `LICENSE` 保留原始 MIT 版权声明（法律要求，不能删除），不属于 UI/品牌标识

## 三、验证

- `pytest tests`：102 passed
- `npm run lint`：0 errors / 3,277 warnings
- `npm run build:prod`：exit 0
- `npm run type-check`：1,823 条存量错误（删除历史组件后进一步下降）
- `rg -i "ruoyi|若依|y_project" src package.json README.md SstyleREADME.md`：源码/文档品牌字样清零，仅 `LICENSE` 保留 MIT 原始版权

## 四、保留边界

- `permission.ts` 使用 `import.meta.glob('./../../views/**/*.vue')`，`views/**` 可能被后台 `sys_menu` 动态挂载，因此不能仅凭 0 import 删除后台页；本轮只删了静态路由/seed 菜单均无的页面。
- `views/monitor/druid` 仍是 seed 菜单页，但后端 FastAPI 无 `/druid` 端点，属于后续功能裁剪，不在本轮品牌清理范围。
- `src/assets/icons/svg` 89 个通用图标不含品牌标志，保留。
