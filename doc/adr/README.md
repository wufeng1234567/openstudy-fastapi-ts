# Architecture Decision Records

本目录记录已做过的关键技术与产品架构决策；新决策使用 `NNNN-title.md`，状态为 `proposed / accepted / superseded / deprecated`。

## 索引

| 编号 | 决策 | 状态 |
|---|---|---|
| [0001](0001-fastapi-custom-agent-loop.md) | FastAPI + 自研 Agent Loop（不引入 LangGraph） | accepted |
| [0002](0002-postgres-pgvector-no-neo4j.md) | PostgreSQL + pgvector，不引入 Neo4j | accepted |
| [0003](0003-graph-contract-and-four-services.md) | GraphNode/GraphEdge 契约、稳定边 ID、四套图谱服务收口 | accepted（部分实现） |
