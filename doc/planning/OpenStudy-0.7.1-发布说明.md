# OpenStudy 0.7.1 发布说明：图片描述任务持久化

> 0.7.1 是 0.7.0 的补丁版本，不改变数据模型和主界面结构，只修复图片批量补全描述的等待体验。

## 问题

原 `/rag/gallery/describe` 在请求里同步串行调用视觉模型：

- 几十张图片要等很久；
- 浏览器离开画廊后，组件销毁，`describing` 进度条消失；
- 再回到画廊时，用户不知道任务还在跑、跑到哪了。

## 修复

- 新增 `rag_image_describe_job` 任务表：`status / total / done / failed / current_asset_key / asset_keys / finished_at`。
- `POST /rag/gallery/describe` 改为创建后台任务并立即返回 `jobId`。
- 后台任务使用 3 路并发调用视觉模型，逐张回写任务进度。
- 新增：
  - `GET /rag/gallery/describe/jobs/latest`
  - `GET /rag/gallery/describe/jobs/{job_id}`
- 画廊重新进入时自动读取最近任务：
  - 运行中 → 恢复进度条、完成/失败计数、当前图片；
  - 已完成 → 刷新卡片和统计；
  - 任务状态落库，切换页面不会中断。
- 单张「生成描述」也复用同一任务机制。
- 画廊详情移除「复制图片」按钮，减少无关操作。
- 画廊支持按文档筛选，文档下拉同时显示每份资料的图片数量；筛选会真正传到后端，不仅过滤当前页 DOM。
- 修复图片「定位原文」：阅读器先结束 loading 再挂载正文，按真实 `offset` 定位；定位失败时用章节标题兜底，不再固定停在文章开头。

## 验证

- 后端真实 API：创建 2 张图片任务，返回 `jobId=1`；轮询从 `running 0/2` 到 `done 2/2`，图片描述成功写回。
- 后端编译通过。
- 前端 `npx vite build --mode development`：通过。
- 比赛 PPT 已用同一稳定文件名 `OpenStudy-10页-码道版.pptx` 覆盖更新，不再新增版本文件。
