# Archived: deprecated DeepSeek web-free reverse proxy

This directory is a source snapshot of the old `apps/deepseek-llm-proxy` Java project,
kept **only on the GitHub branch** `backup/deepseek-web-free-proxy`.

It is **not used by the main branch**. The main branch uses the official DeepSeek
Search / Fetch API instead:

- `openstudy-fastapi/app/services/ai/web_search_service.py`
- `openstudy-fastapi/app/services/ai/agent/tools/web_search.py`
- `GET /rag/study-plan` / `web_search` agent tool docs:
  `doc/planning/废弃DeepSeek网页免费反代与官方Search-Fetch迁移.md`

The original directory was removed from the working machine on 2026-11-08 after this
snapshot was committed. Gitee and GitCode do not keep this backup branch.
