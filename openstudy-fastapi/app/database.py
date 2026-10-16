"""
数据库连接配置
使用 SQLAlchemy 2.0 异步引擎 + asyncpg
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
from loguru import logger



# 当前方言（供 init_db 里的兼容代码决定要不要执行 MySQL 专有 DDL）
IS_POSTGRES = settings.IS_POSTGRES

# 创建异步引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # 禁用 SQL 日志输出
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# 创建异步会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# 基础模型类
class Base(DeclarativeBase):
    pass


async def get_db():
    """
    获取数据库会话的依赖函数
    自动处理事务提交和回滚
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def register_all_models() -> None:
    """把所有 ORM 模型注册进 `Base.metadata`。

    ⚠️ **必须只有这一份清单**。曾经 `init_db()` 和迁移脚本各维护一份，
    结果加了新模型只更新了一边 —— `init_db` 建得出表、迁移脚本却「查无此表」。
    任何需要完整 metadata 的地方（建表、数据迁移、反射）都调这个函数。
    """
    from app.models import (  # noqa: F401
        agent_config,
        agent_memory,
        agent_op_log,
        agent_role_pref,
        agent_tool_pref,
        ai_chat,
        ai_config,
        bank_share,
        config,
        courses,
        menu,
        note,
        note_question,
        note_question_bank,
        notice,
        notification,
        question,
        role,
        user,
        words,
    )
    # ⚠️ 这 4 个模块把 ORM 模型内联定义在 api/v1 里（历史写法），不在 app/models 下。
    #    不导入它们 → 对应的表不会被 create_all 建出来。
    #    MySQL 上因为表早已存在所以一直没暴露，迁移到新 PG 库会直接报
    #    `relation "carousel" does not exist`（以及另三张）。
    from app.api.v1 import carousel, chat, leave_message, sensitive_word  # noqa: F401

    # RAG 四表是 **PG 专有**（vector(1024) / tsvector 生成列 MySQL 都没有）。
    # 只在 PG 下导入，否则用 DB_DRIVER=mysql 回滚时 create_all 会直接报 DDL 错误。
    if IS_POSTGRES:
        from app.models import rag  # noqa: F401


async def init_db():
    """初始化数据库（创建表）"""
    async with engine.begin() as conn:
        register_all_models()

        # PostgreSQL 专用：建表前先确保扩展存在。
        #   vector   → rag_document_chunk.embedding 的向量列与 HNSW 索引
        #   pg_trgm  → 中文/模糊检索的 gin_trgm_ops 索引
        # 必须排在 create_all **之前**，否则用到 vector 类型的表会建不出来。
        if IS_POSTGRES:
            def _ensure_pg_extensions(sync_conn):
                from sqlalchemy import text
                for ext in ("vector", "pg_trgm"):
                    try:
                        sync_conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
                    except Exception as e:  # pragma: no cover - 权限不足时降级
                        logger.warning(
                            f"创建扩展 {ext} 失败（RAG 向量/模糊检索将不可用）: {e}"
                        )

            await conn.run_sync(_ensure_pg_extensions)

        # 创建所有表
        await conn.run_sync(Base.metadata.create_all)

        # 兼容历史库：create_all 不会给已存在的表新增列，这里手动补齐
        def _ensure_question_bank_columns(sync_conn):
            from sqlalchemy import inspect, text
            inspector = inspect(sync_conn)
            if "question_bank" not in inspector.get_table_names():
                return
            columns = {c["name"] for c in inspector.get_columns("question_bank")}
            if "allow_fork" not in columns:
                sync_conn.execute(text(
                    "ALTER TABLE question_bank ADD COLUMN allow_fork INTEGER NOT NULL DEFAULT 1"
                ))
                logger.info("question_bank.allow_fork 列已补齐")

        await conn.run_sync(_ensure_question_bank_columns)

        # 兼容历史库：sys_ai_config 新增 DeepSeek 网页端反代凭据字段
        def _ensure_ai_config_columns(sync_conn):
            from sqlalchemy import inspect, text
            inspector = inspect(sync_conn)
            if "sys_ai_config" not in inspector.get_table_names():
                return
            columns = {c["name"] for c in inspector.get_columns("sys_ai_config")}
            added = []
            if "web_phone" not in columns:
                sync_conn.execute(text(
                    "ALTER TABLE sys_ai_config ADD COLUMN web_phone VARCHAR(50) NULL"
                ))
                added.append("web_phone")
            if "web_password" not in columns:
                sync_conn.execute(text(
                    "ALTER TABLE sys_ai_config ADD COLUMN web_password VARCHAR(200) NULL"
                ))
                added.append("web_password")
            if "web_area_code" not in columns:
                sync_conn.execute(text(
                    "ALTER TABLE sys_ai_config ADD COLUMN web_area_code VARCHAR(10) NULL"
                ))
                added.append("web_area_code")
            if "model_kind" not in columns:
                sync_conn.execute(text(
                    "ALTER TABLE sys_ai_config ADD COLUMN model_kind VARCHAR(20) NULL"
                ))
                added.append("model_kind")
            if added:
                logger.info(f"sys_ai_config 列已补齐: {', '.join(added)}")

        await conn.run_sync(_ensure_ai_config_columns)

        # 兼容历史库：rag_knowledge_base 新增「屏蔽」开关列（0=启用，1=已屏蔽）。
        # ⚠️ **`create_all` 只建缺失的表，绝不给已存在的表加列** —— 线上这张表早就在了，
        #    所以必须在这里手动补。反过来，表是这一趟刚由 `create_all` 建出来的话，
        #    `get_columns` 里已经能看到 disabled，这个分支自动跳过（幂等）。
        # ⚠️ 判据是**表是否存在**，不是 `IS_POSTGRES`：用 `DB_DRIVER=mysql` 回滚时
        #    rag 模块压根不会被导入（见 `register_all_models`），那时表根本不存在，
        #    inspector 已经挡住了；写成 IS_POSTGRES 反而会在「PG 库还没建 rag 表」时踩空。
        def _ensure_rag_kb_columns(sync_conn):
            from sqlalchemy import inspect, text
            inspector = inspect(sync_conn)
            if "rag_knowledge_base" not in inspector.get_table_names():
                return
            columns = {c["name"] for c in inspector.get_columns("rag_knowledge_base")}
            if "disabled" not in columns:
                sync_conn.execute(text(
                    "ALTER TABLE rag_knowledge_base "
                    "ADD COLUMN disabled SMALLINT NOT NULL DEFAULT 0"
                ))
                logger.info("rag_knowledge_base.disabled 列已补齐（默认 0 = 启用）")

        await conn.run_sync(_ensure_rag_kb_columns)

        # 兼容历史库：rag_document 新增「图片清单」列（键=【图N】的 N，值=/profile/... 相对路径）。
        # 图片从「解析后被丢弃」变成可检索/可回传给模型（见 app/models/rag.py 的 image_map 注释）。
        def _ensure_rag_document_columns(sync_conn):
            from sqlalchemy import inspect, text
            inspector = inspect(sync_conn)
            if "rag_document" not in inspector.get_table_names():
                return
            columns = {c["name"] for c in inspector.get_columns("rag_document")}
            if "image_map" not in columns:
                sync_conn.execute(text(
                    "ALTER TABLE rag_document ADD COLUMN image_map JSON NULL"
                ))
                logger.info("rag_document.image_map 列已补齐（文档图片清单）")

        await conn.run_sync(_ensure_rag_document_columns)

        # 兼容历史库：ai_agent_memory 新增「逻辑删除」列（未删 / 已删可恢复）。
        # ⚠️ 与上一条同理：`create_all` **只建缺失的表，不给已存在的表加列** ——
        #    这张表是 SpringBoot 时代建的（实测 7 列：id/user_id/memory_type/content/
        #    metadata/importance/create_time，**没有任何状态列**），所以必须在这里手动补。
        #    不补的后果不是「少个功能」而是**整个记忆模块直接报错**：
        #    `AiAgentMemory` 一旦带上 `del_flag`，ORM 每次查询都会带上它 →
        #    `UndefinedColumn: column ai_agent_memory.del_flag does not exist`。
        # ⚠️ 取值口径与 `note.del_flag` 完全一致：`'0'` = 未删、`'2'` = 已删（可在
        #    「最近删除」里恢复）。旧行靠 `DEFAULT '0'` 回填。
        # ⚠️ 这个 `DEFAULT '0'` **必须留着**，不是多余的：这张表还有**裸 SQL INSERT** 在写
        #    （`tests/e2e_agent_api.py` 的 P14/P18 夹具只给 user_id/memory_type/content/
        #    importance 四列），库侧没有默认值时那些 INSERT 会直接因 NOT NULL 失败。
        # ⚠️ 判据同样是**表是否存在**（不是 `IS_POSTGRES`）：这张表两边都有，与 rag 那条同理。
        def _ensure_agent_memory_columns(sync_conn):
            from sqlalchemy import inspect, text
            inspector = inspect(sync_conn)
            if "ai_agent_memory" not in inspector.get_table_names():
                return
            columns = {c["name"] for c in inspector.get_columns("ai_agent_memory")}
            if "del_flag" not in columns:
                sync_conn.execute(text(
                    "ALTER TABLE ai_agent_memory "
                    "ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT '0'"
                ))
                logger.info("ai_agent_memory.del_flag 列已补齐（默认 '0' = 未删）")

        await conn.run_sync(_ensure_agent_memory_columns)

        # 兼容历史库：ai_chat_message 新增「轮次 id + 逻辑删除」两列（回退本轮对话用）。
        # ⚠️ 与上面两条同理：`create_all` **只建缺失的表，不给已存在的表加列** ——
        #    这张表是早就建好的（实测 7 列：id/session_id/user_id/role/content/
        #    attachments/create_time，**既没有 turn_id 也没有 del_flag**），所以必须手动补。
        #    不补的后果不是「少个功能」而是**整个聊天历史直接报错**：ORM 一旦带上这两个属性，
        #    每次读写都会带上它们 → `UndefinedColumn: column ai_chat_message.turn_id
        #    does not exist`（与 ai_agent_memory 当年那次一模一样）。
        # ⚠️ 取值口径与 `note.del_flag` / `ai_agent_memory.del_flag` 一致：`'0'` = 未删、
        #    `'2'` = 已删。旧行靠 `DEFAULT '0'` 回填。
        # ⚠️ 裸 SQL 的 DEFAULT **必须写全**（`NOT NULL DEFAULT ...`）：这两列在模型里是
        #    非空且只有 Python 侧 default，库侧没有默认值时，历史行回填不成、且任何
        #    「只写老列」的裸 SQL INSERT（探针夹具）都会因 NOT NULL 直接失败。
        # ⚠️ 判据同样是**表是否存在**（不是 `IS_POSTGRES`）—— 与 rag_kb / agent_memory 两条同理。
        def _ensure_ai_chat_message_columns(sync_conn):
            from sqlalchemy import inspect, text
            inspector = inspect(sync_conn)
            if "ai_chat_message" not in inspector.get_table_names():
                return
            columns = {c["name"] for c in inspector.get_columns("ai_chat_message")}
            added = []
            if "turn_id" not in columns:
                sync_conn.execute(text(
                    "ALTER TABLE ai_chat_message "
                    "ADD COLUMN turn_id VARCHAR(64) NOT NULL DEFAULT ''"
                ))
                added.append("turn_id")
            if "del_flag" not in columns:
                sync_conn.execute(text(
                    "ALTER TABLE ai_chat_message "
                    "ADD COLUMN del_flag VARCHAR(1) NOT NULL DEFAULT '0'"
                ))
                added.append("del_flag")
            if added:
                logger.info(f"ai_chat_message 列已补齐: {', '.join(added)}")

        await conn.run_sync(_ensure_ai_chat_message_columns)

        # 兼容历史库：AI 会话表转 utf8mb4。
        # create_all 建表时会跟随库的默认字符集，若库默认是 utf8mb3（3 字节），
        # 内容里的 emoji（4 字节 UTF-8）会写入失败：
        #   (1366, "Incorrect string value: '\\xF0\\x9F...' for column 'content'")
        # ⚠️ MySQL 专有（information_schema.TABLES / CONVERT TO CHARACTER SET 都是
        #     MySQL 方言）。PG 建库即 UTF8，无此问题，直接跳过。
        def _ensure_ai_chat_utf8mb4(sync_conn):
            if IS_POSTGRES:
                return
            from sqlalchemy import inspect, text
            inspector = inspect(sync_conn)
            tables = set(inspector.get_table_names())
            for table in ("ai_chat_session", "ai_chat_message"):
                if table not in tables:
                    continue
                collation = ""
                try:
                    row = sync_conn.execute(text(
                        "SELECT TABLE_COLLATION FROM information_schema.TABLES "
                        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"
                    ), {"t": table}).fetchone()
                    collation = (row[0] if row else "") or ""
                except Exception:
                    collation = ""
                if collation.startswith("utf8mb4"):
                    continue
                sync_conn.execute(text(
                    f"ALTER TABLE {table} CONVERT TO CHARACTER SET utf8mb4 "
                    "COLLATE utf8mb4_general_ci"
                ))
                logger.info(f"{table} 已转换为 utf8mb4（原 {collation or '未知'}）")

        await conn.run_sync(_ensure_ai_chat_utf8mb4)

        # 兼容历史库：ai_chat_message 的正文 / 附件列要够长。
        # 早期建表用的是 TEXT（上限 64KB），而一张 240px 缩略图 base64 后就有
        # 30~50KB，多图那一轮的 JSON 会写不进去 —— 报 (1406) Data too long，
        # 整个事务回滚，表现为「带图片的那轮历史存不上」。这里统一升到 MEDIUMTEXT。
        # ⚠️ 同样 MySQL 专有（PG 的 TEXT 无长度上限，MEDIUMTEXT 类型也不存在）。
        def _ensure_ai_chat_longtext(sync_conn):
            if IS_POSTGRES:
                return
            from sqlalchemy import inspect, text
            inspector = inspect(sync_conn)
            if "ai_chat_message" not in inspector.get_table_names():
                return
            col_types = {
                c["name"]: str(c.get("type", "")).lower()
                for c in inspector.get_columns("ai_chat_message")
            }
            for col in ("content", "attachments"):
                if col_types.get(col) in ("text", "tinytext"):
                    sync_conn.execute(text(
                        f"ALTER TABLE ai_chat_message MODIFY COLUMN {col} MEDIUMTEXT NULL"
                    ))
                    logger.info(f"ai_chat_message.{col} 已扩容为 MEDIUMTEXT")

        await conn.run_sync(_ensure_ai_chat_longtext)
        logger.info("Database tables created successfully")


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
    logger.info("Database connections closed")
