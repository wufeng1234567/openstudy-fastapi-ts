---
name: knowledge_ingest 智能体入库工具的设计方案
description: 用户认可的智能体写入库工具方案——knowledge_ingest 支持 from_text/from_attachment，落库同步+向量化后台，无需确认但需确认卡片
type: project
from: Agent
---

2026-10-09，针对"让智能体自主完成文档入库到知识库"的需求（详见 project-agent-kb-doc-tool-scope），Agent 给出并经用户**确认记录**的实现方案：

**新增 Agent 工具 `knowledge_ingest`**（位于 `app/services/ai/agent/tools/knowledge_ingest.py`），**不复用** `knowledge_base_manage` 的 action（一工具一职责，降低模型选错概率）：
- `from_text`：将一段文本（模型的总结/笔记/生成内容）写入指定知识库。
- `from_attachment`：将**用户本轮上传的附件正文**写入知识库，正文取 `ctx.extra["attachments"]`。

**核心机制（方案 B：解析同步 + 向量化后台）**：execute 内自行开独立 `async_session_factory` 会话，`rws.create_document(status=DOC_PENDING)` 落库拿 `doc_id`，再 `asyncio.create_task(document_pipeline.process_document(doc_id))` 后台跑分块+embedding，工具**立即返回** ok(docId, status="处理中", message="已入库，正在向量化...")。不在工具内同步分块，保持单一数据通路（`process_document` 是唯一入口），避免 chunk 逻辑漂移。
- **不被 SAVEPOINT 卡住**：工具虽 `write_operation=True`，但**自己开会话**（同 `knowledge_base_manage` 做法），`ctx.db` 只用于只读校验。
- **确认卡片** `needs_confirmation=True`（所有 action），`preview()` 用 `chunk_text` 预估块数但**不落库、不调 embedding**（如"将向【计算机网络】写入约 12 块，需 1 次向量化调用"）；`is_destructive=False`。
- **限额**：沿用 `MAX_CHUNKS=100`（chunker）、`MAX_DOCS_PER_KB=200`（rws）双重兜底，工具层再拒空正文/超长。
- **回退声明**：`from_text` 的逆 = 物理删该文档，标 `undoable=True`（本次新建、干净可撤）；如涉及分块重建成本则用 `REASON_CONTENT_DESTROYED` 等。

**附带改动**：① `loop.py` 组装 ctx 时注入 `extra={"attachments":[{"name":..., "text":...}]}`（数据来自 `_collect_attachments`，需让其同时返回结构化列表）；② `tools/__init__.py` 注册新工具；③ 不做服务器文件路径入库，不做全异步。

**Why:** 用户要放行被刻意禁止的 `create_document`/`replace_chunks` 能力（原因涉付费 embedding），本方案在放行能力的同时控制成本与用户等待体验。
**How to apply:** 若继续实现该工具，按此设计执行；重点：独立会话避免 SAVEPOINT 冲突、embedding 用后台任务推走、确认卡片只预估不落库、`process_document` 为唯一分块入口。测试用 mock `embed_texts` 防花钱，复用仓库既有 `tests/_probe_*` 风格。

**2026-10-09 测试落地**：已按此设计写好纯逻辑 probe `tests/_probe_knowledge_ingest.py` 并跑通 27/28（唯一失败的 KI-20 源于测试 mock 过宽，非工具缺陷）。测试细节与踩坑（staticmethod 恢复、kb 归属校验依赖 create_document 内部逻辑）见 project_agent_knowledge_ingest_plan.md 的「测试」小节。

**2026-10-09 手工验收脚本（用户要求）：** 用户要了一组**测试提示词**验证「智能体知识库写入能力」，覆盖：① 建库→`from_text` 写入→`from_attachment` 附件写入→`knowledge_search` 检索闭环→`list_documents` 查 status（最终应为 5 已向量化）→边界/拒绝分支（无附件 from_attachment、空内容、越权 kb id=999999）→回退物理删除。**关键观察点**：确认卡片必须显示「块数 + embedding 调用次数估算」（成本闸门）；确认后**秒回**「正在向量化」而非卡住；文档 status 流转 1→2→3→5（失败 4）；写入期间 Agent 流不阻塞。前提：后端已启动、`knowledge_base_manage` 与 `knowledge_ingest` 均已启用。
