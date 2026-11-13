# OpenStudy Architecture

> One-page architecture for evaluators and new contributors.
> Runtime source of truth: FastAPI + PostgreSQL/pgvector + Redis; frontend: Vue 3 + TypeScript + Vite.

## 1. System shape

```text
Browser
  └─ Vue 3 SPA (openstudy-vue3-ts)
       ├─ Router / Pinia / API clients
       ├─ Views: workspace / studio / question practice / notes / English / agent
       └─ Agent assistant drawer
                 │ HTTP / SSE
                 ▼
       FastAPI (openstudy-fastapi)
       ├─ API layer: app/api/v1
       ├─ Services: app/services
       │    ├─ AI agent loop / tools / memory
       │    └─ RAG: parse → chunk → embed → retrieve → wiki / graph
       ├─ Models / schemas / repositories
       └─ PostgreSQL + pgvector, Redis
```

## 2. Frontend boundaries

```text
src/
  api/          typed API clients by domain
  components/   reusable presentational components
  composables/  stateful / side-effect reusable logic
  layouts/      page shells
  router/       routes and guards
  stores/       Pinia state
  styles/       global styles and tokens
  types/        domain types
  utils/        pure helpers
  views/        page orchestration only
```

Rule: `views` orchestrate, `components` render, `composables` own state/side effects, `utils` stay pure. Large views should be split rather than accumulating business logic.

## 3. Backend boundaries

```text
app/
  api/v1/       routes: validation, auth, response mapping
  core/         config, logging, security, exceptions
  models/       ORM models
  schemas/      Pydantic request/response schemas
  services/     business logic
    ai/         agent loop, tools, memory, model routing
    rag/        document parsing, chunking, embedding, retrieval, wiki, graph
  repositories/ data access helpers
  db/           sessions / initialization
  migrations/   versioned database migrations (target: Alembic)
  utils/        pure utilities
```

Rule: routes stay thin; business rules live in services; database changes must be reversible and versioned.

## 4. Main runtime flows

- **Document ingestion**: upload → parse (docx/pdf/md/txt/images) → chunks → embeddings → retrieval index → document health / smart report → wiki page / graph entities.
- **Agent chat**: user message → tool selection → read/write tool execution → confirmation for writes → evidence-bearing answer → memory / trace.
- **Practice**: bank → paper / questions → answer → server grading → result / wrong-question state.
- **Knowledge graph**: source entities → graph contract (`GraphNode` / `GraphEdge`) → topic / source / question / note relations → UI projection.

## 5. Quality and operational boundaries

- CI: `.github/workflows/ci.yml` performs backend syntax/import/pytest/ruff, frontend build, repository hygiene.
- Current honest baseline (2026-11-13): pytest 109 collected, ruff syntax gate pass, frontend lint 0 errors / 4,156 warnings; type-check is historical reference only and is not a gate.
- Known structural debt: some oversized views/services, four historical graph service layers, and legacy RuoYi pages that still carry type debt.
- Secrets: real `.env` files are not committed; use `.env.example`; see `SECURITY.md`.

## 6. Deployment

`docker-compose.yml` defines local PostgreSQL/Redis and application services. Startup scripts live in `startup-scripts/` (Windows `.bat` for this project). Production requires explicit environment variables and a restored database migration plan; see `doc/deploy/`.
