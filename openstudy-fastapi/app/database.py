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


async def init_db():
    """初始化数据库（创建表）"""
    async with engine.begin() as conn:
        # 导入所有模型以确保它们被注册
        from app.models import (
            user, role, menu, notice, question, note,
            note_question_bank, note_question,
            courses, words, config,
            bank_share, notification,
        )

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
        logger.info("Database tables created successfully")


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
    logger.info("Database connections closed")
