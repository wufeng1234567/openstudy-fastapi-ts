"""
敏感词 API - 完整实现
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.core.security import require_admin
from app.core.response import success, paginate, error
from app.utils.excel_util import export_to_excel
from datetime import datetime

router = APIRouter(prefix="/sensitiveWord/sensitiveWord")

from sqlalchemy import BigInteger, String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SensitiveWord(Base):
    __tablename__ = "sys_sensitive_word"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(1), default="0")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def format_word(item):
    return {
        "id": item.id,
        "word": item.word,
        "level": item.level,
        "status": item.status,
        "createTime": item.create_time.isoformat() if item.create_time else None,
    }


@router.get("/list")
async def list_sensitive_words(
    word: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    query = select(SensitiveWord)
    if word:
        query = query.where(SensitiveWord.word.ilike(f"%{word}%"))
    if status:
        query = query.where(SensitiveWord.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(SensitiveWord.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    items = list(result.scalars().all())

    return paginate(total, [format_word(i) for i in items])


@router.post("")
async def create_sensitive_word(
    word: str = Query(...),
    level: Optional[int] = Query(1),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    # 检查是否已存在
    check_query = select(SensitiveWord).where(SensitiveWord.word == word)
    check_result = await db.execute(check_query)
    if check_result.scalar_one_or_none():
        return error("敏感词已存在")

    item = SensitiveWord(word=word, level=level)
    db.add(item)
    await db.flush()
    # 失效过滤器缓存,使下次检查重新加载
    from app.services.sensitive_filter import invalidate_cache
    invalidate_cache()
    return success(format_word(item))


@router.put("")
async def update_sensitive_word(
    id: int = Query(...),
    word: Optional[str] = Query(None),
    level: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    query = select(SensitiveWord).where(SensitiveWord.id == id)
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if not item:
        return error("敏感词不存在")

    if word is not None:
        item.word = word
    if level is not None:
        item.level = level
    if status is not None:
        item.status = status

    # 失效过滤器缓存,使下次检查重新加载
    from app.services.sensitive_filter import invalidate_cache
    invalidate_cache()
    return success()


@router.delete("/{ids}")
async def delete_sensitive_words(
    ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    id_list = [int(id) for id in ids.split(",")]
    stmt = delete(SensitiveWord).where(SensitiveWord.id.in_(id_list))
    await db.execute(stmt)
    # 失效过滤器缓存,使下次检查重新加载
    from app.services.sensitive_filter import invalidate_cache
    invalidate_cache()
    return success()


@router.post("/export")
async def export_sensitive_words(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """导出敏感词列表为 Excel"""
    query = select(SensitiveWord).order_by(SensitiveWord.create_time.desc())
    result = await db.execute(query)
    items = list(result.scalars().all())

    rows = [{
        "id": i.id,
        "word": i.word,
        "level": i.level,
        "status": "正常" if i.status == "0" else "停用",
        "createTime": i.create_time.isoformat() if i.create_time else "",
    } for i in items]

    headers = [
        {"key": "id", "label": "ID"},
        {"key": "word", "label": "敏感词"},
        {"key": "level", "label": "等级"},
        {"key": "status", "label": "状态"},
        {"key": "createTime", "label": "创建时间"},
    ]

    return export_to_excel(rows, headers, "sensitiveWord")
