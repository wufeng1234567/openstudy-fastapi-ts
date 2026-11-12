# ADR 0002: PostgreSQL + pgvector，不引入 Neo4j

- 状态：accepted
- 日期：2026-11-12（整理既有决策）

## 背景

资料、向量检索、知识百科、实体关系、题源和笔记关系需要共用一个可部署、可备份的数据面。

## 决策

使用 PostgreSQL 16 + pgvector + pg_trgm/GIN：向量、全文、实体/关系表都在同一个数据库；不引入 Neo4j。

## 后果

- 正面：部署轻、备份/恢复链路统一、事务边界统一。
- 负面：复杂图算法、超大图缓存和跨来源图查询能力有限；需要通过 `study_map_service` 物化/裁剪，不能把 PG 当图数据库宣传。

## 验证

- RAG 流水线：`app/services/rag/hybrid_search.py`（向量 + 关键词 + RRF）；
- 实体/关系表：`rag_graph_entity`、`rag_graph_relation`；
- 图谱当前只适合中等规模资料夹，已知规模边界写入系统介绍与质量报告。
