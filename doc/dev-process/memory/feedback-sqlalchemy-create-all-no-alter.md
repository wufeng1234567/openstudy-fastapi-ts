---
name: SQLAlchemy create_all 不改已存在表结构（JSON 类型坑）
description: init_db/create_all 幂等、不会 ALTER 既有表；曾因先按早期 Text 定义建表、后改 JSON 而 DB 列仍是 text，asyncpg 拒收 list
type: feedback
from: Agent
---

**规则：** 新增/修改 SQLAlchemy 模型列类型后，若该表之前已用旧类型建过（`create_all`/`init_db` 幂等，只建缺的表、**绝不修改已存在列的列类型**），DB 里会保留旧类型。改列类型后必须显式处理已建表。

**Why:** 2026-10-09 实施阶段2骨架时，`tools: Mapped[Optional[list]] = mapped_column(JSON)` 本应产出 json 列，但查 DB 实际是 **text**——因为 `init_db`（create_all）在该列还是最早 `Text` 版本时就建过表，之后改成 `JSON` 也不会改列。写入 list 时 asyncpg 报错（列期望 str）。新表无数据，采用 **DROP TABLE 后重新 init_db** 重建。

**How to apply:** 改列类型（尤其 Text→JSON）后，用查询脚本确认 DB 真实列类型，别只信模型定义；开发期新表无数据直接删表重建即可（`create_all` 不会自动迁移）。参考：`agent_memory.meta_data` 用 `mapped_column("metadata", JSON)` 工作正常。2026-10-09 已删表重建并验证 `ai_agent_config.tools` 实际列类型确为 `json`。

**2026-10-11 沙箱内验证新表 DDL 的可复用技法（判定属于本条扩展）：** 沙箱 asyncio 全挂（见 feedback-sandbox-blocks-asyncio-event-loop）→ **`create_all` 跑不了（需 async）**。改为：**用 SQLAlchemy 的 `CreateTable` 同步生成 DDL 字符串**（`str(CreateTable(Model.__table__).compile(...))`，**纯同步、不需连 DB**），与手写/手建表的 DDL 逐字段核对。核对前提=**先 `register_all_models()`**（否则 `sys_user` 等模型未注册，见 feedback-probe-register-all-models）。

**同类坑（手建表须与模型一致）：** 沙箱内要端到端读写时，用**同步 psycopg2 手工 `CREATE TABLE`** 建表（绕过 async `create_all`），但与模型可能**逐字不一致**——实测 `user_note_draft.is_public` 手建为 `INTEGER DEFAULT 1`（可空），模型为 `NOT NULL`（无 server default）；**应用层都会赋值故无碍**，但**核对时要意识到这层差异**，别把"字段名/类型齐全"误判为"与模型完全等同"。**How to apply:** 沙箱内想验证某模型表结构时，优先走「`CreateTable` 生成 DDL 字符串 vs 模型/手建表」的同步对比；手建表仅用于读写验证，须注明可能与模型的 nullable/default 差异。
