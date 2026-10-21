---
name: PG 库（localhost:5432）沙箱同步直连查偏好表
description: 2026-10-11 沙箱 asyncio 全挂时查偏好表与题库数据的办法——读 .env 拿 PG 连接串（库 openstudy_v2_pgsql），用 psycopg2 同步直连
type: reference
from: Agent
---

排查「用户偏好是否全量屏蔽」等需要读库的场景：

- 项目 PostgreSQL 在 **`localhost:5432`**；连接参数从项目 **`.env`** 读取（主工作区才有 `.env`，worktree 无 `.env`）。
- **2026-10-11 已核实 `.env` 实际值**：`DB_DRIVER=postgres`（改 `mysql` 可回滚 MySQL，业务代码无需改）、主机 `localhost:5432`、库名 **`openstudy_v2_pgsql`**、用户 `root`、密码 `123456`；连接串 `postgresql://root:123456@localhost:5432/openstudy_v2_pgsql`。
- 沙箱内 **asyncpg / `aiomysql` 都用不了**（事件循环建不起来，见 `feedback-sandbox-blocks-asyncio-event-loop`）→ 改**同步驱动 `psycopg2` 直连**。
- 关键偏好表：`ai_agent_tool_pref`（用户屏蔽的工具，本行"关工具"语义作用的表）、`ai_agent_role_pref`（用户禁用的专家，专家开关作用的新表）。
- 只读探针入口：`openstudy-fastapi\tests\_probe_db_pref.py`；
- 题库数据探查探针（2026-10-11 新增）：`openstudy-fastapi\tests\_probe_qbank_data.py`（查某题库题目实际存储的题面文本，用于判"表格显示异常是否数据问题"）。**注：首探因 `question_bank`/`question_main` 表结构与臆测不符而失败；实际题目表列名为 `bank_name`（探针已改用 `bank_name`）；「概率论与数理统计题库」= `bank=1175`（用户新建、4 题）。**2026-10-11 该库已完整读出：4 题中仅 `id=2772`（二维随机变量）题干含表格，其库内真实存储为**竖线形态** `X\Y | 0 | 1 | 2`（裸竖线、无 `| --- |` 分隔行），**不是制表符 `\t`**——用户贴出的 `\t` 形态属展示/复制层 Tab 化产物；**故"表格不渲染"未必是数据问题，读库与"贴出的文本"可能形态不一致，须以库内原样文本为准。**
- **2026-10-11 补充（`id=2772` 结构瑕疵）**：`bank=1175` 中 `id=2772` 的 `question_type=5`（essay/问答题），但其 `answer` 字段塞了**完整答案+解析**、题干里还有 `<img>`——属**导入时"组合式内容塞进单字段"的结构问题**（与"表格不渲染"无关）。
- 沙箱探测命令（Windows cmd）：`netstat -ano | findstr "LISTENING" | findstr "127.0.0.1:5432"`。
