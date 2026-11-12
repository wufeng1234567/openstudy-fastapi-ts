# ADR 0003: GraphNode/GraphEdge 契约与四套图谱服务

- 状态：accepted（部分实现）
- 日期：2026-11-12（整理既有决策）

## 背景

历史上积累四套图谱服务：`knowledge_graph_service`（实体图）、`wiki_service`（页面图）、`study_graph_service`（旧学习图）、`study_map_service`（六类统一图）。不同服务的 node/edge 字段与边 ID 生成方式不一致，前端出现碎片化入口与证据漂移。

## 决策

1. 统一 `GraphNode` / `GraphEdge` 契约，字段包含稳定 `id`、`type`、`label`、`sourceRefs`；
2. 边 ID 由 `sha1(source->target)[:16]` 派生为稳定值，不使用 `len(edges)+1`；
3. `study_map_service` 作为六类统一图的目标服务；旧服务保留兼容但不再新增能力；
4. 前端只保留“知识百科/知识图谱”入口，不另设“六类图”独立入口。

## 后果

- 正面：建议 trace、前端 edge key、来源证据可对齐；减少重复实现。
- 负面：四套服务收口不是一次性删除，需兼容期；`KnowledgeWikiPanel` 大文件仍需 P2 拆分。

## 验证

- `app/services/rag/graph_contract.py`；
- `study_map_service` / `knowledge_map_service` 已使用稳定边 ID；
- 质量报告记录“图谱评级 6/10，真实数据但未完全产品化”。
