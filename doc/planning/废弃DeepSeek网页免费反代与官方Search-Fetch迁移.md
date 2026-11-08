# 废弃 DeepSeek 网页免费反代，迁移到官方 Search / Fetch

日期：2026-11-08

## 结论（给未来的 LLM / 维护者）

- `D:\OpenStudy\apps\deepseek-llm-proxy` 是旧的 **DeepSeek 网页版免费反代** 多模块 Java 工程：
  手机号登录 `chat.deepseek.com`、PoW/WASM 风控、浏览器扩展 DOM 自动化、`ProviderMode.WEB`
  「联网模式」都属于这条链路。
- 它已**废弃**，不属于 OpenStudy 主分支的产品方向。主分支明确不再使用「DeepSeek 网页版本免费反代」。
- 备份位置：只推送到 **GitHub** 的 `backup/deepseek-web-free-proxy` 分支。Gitee / GitCode
  不保留该分支，只保留最新主分支。
- 替代方案：使用 **DeepSeek 官方公开 API 的 Search / Fetch**（不是网页反代）：
  - `POST https://api.deepseek.com/v1/tools/search`
  - `POST https://api.deepseek.com/v1/tools/fetch`
  - Bearer `DEEPSEEK_API_KEY`，与聊天接口共用同一个官方 Key；
  - 返回真实 `title / url / snippet / summary / site_name / date / authority` 与 Markdown 正文；
  - 代码入口：`openstudy-fastapi/app/services/ai/web_search_service.py`。

## 为什么废弃

1. 网页反代依赖登录态、Cookie、PoW/WASM 与 DOM 选择器，站点改版即失效；
2. 无法提供稳定的结构化引用/索引；
3. 与 OpenStudy「可解释、真实来源、可维护」的方向不符，容易变成假功能；
4. 官方 Search / Fetch 已提供真实、可计费、可审计的搜索与抓取 API，且不需要额外 Key。

## 主分支保留的替代能力

- 智能对话：`web_search` Agent 工具（`app/services/ai/agent/tools/web_search.py`），
  `search` + `fetch`，结果带 `W1/W2...` 索引和真实 URL，前端渲染 `[W1](url)` 且提供来源 chip。
- 知识库手动入口：工作空间「上传文档 → 从网页导入」，可粘贴 URL 或输入关键词搜索后导入；
  后端 `POST /rag/web/search`、`POST /rag/document/importUrl`。
- 网页入库后与普通文档走同一条解析、分块、向量化、知识百科、知识图谱流水线；
  `rag_document.source_url` 保留原始网址。
- Agent 也可用 `knowledge_ingest` action `from_url` 完成网页入库。

## 备份与恢复

- GitHub 分支：`backup/deepseek-web-free-proxy`，提交信息为
  `chore: archive deprecated deepseek-llm-proxy before removal`。
- 恢复方式（仅 GitHub）：
  ```text
  git fetch github backup/deepseek-web-free-proxy
  git checkout backup/deepseek-web-free-proxy
  ```
  快照位于分支的 `doc/legacy/deepseek-llm-proxy/`。
- Gitee / GitCode **没有**这个备份分支。不要在这两个仓库寻找它。

## 清理边界

- 已删除外部目录：`D:\OpenStudy\apps\deepseek-llm-proxy`（源码已进入 GitHub 备份分支）。
- 主分支不再新增任何对网页免费反代的 import、配置项或启动入口。
- 如果未来需要彻底清理 Python 侧遗留模块（`deepseek_web_client.py`、`DEEPSEEK_WEB_*`、
  `ds-free-nb` 桥等），应另开迁移任务，先跑全量回归，不要与本次搜索能力混在一起删除。
