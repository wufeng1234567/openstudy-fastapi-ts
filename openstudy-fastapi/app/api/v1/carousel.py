"""
轮播图 API - 完整实现
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, paginate, error
from app.utils.excel_util import export_to_excel
from datetime import datetime

router = APIRouter(prefix="/carousel/carousel")

# 轮播图模型
from sqlalchemy import BigInteger, String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Carousel(Base):
    __tablename__ = "carousel"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    link_url: Mapped[Optional[str]] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(1), default="0")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def format_carousel(item):
    return {
        "id": item.id,
        "title": item.title,
        "imageUrl": item.image_url,
        "linkUrl": item.link_url,
        "sortOrder": item.sort_order,
        "status": item.status,
        "createTime": item.create_time.isoformat() if item.create_time else None,
    }


@router.get("/list")
async def list_carousel(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = select(Carousel).where(Carousel.status == "0")

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(Carousel.sort_order.asc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    items = list(result.scalars().all())

    return paginate(total, [format_carousel(i) for i in items])


@router.get("/all")
async def list_all_carousel(
    db: AsyncSession = Depends(get_db),
):
    query = select(Carousel).where(Carousel.status == "0").order_by(Carousel.sort_order.asc())
    result = await db.execute(query)
    items = list(result.scalars().all())
    return success([format_carousel(i) for i in items])


@router.get("/{id}")
async def get_carousel(
    id: int,
    db: AsyncSession = Depends(get_db),
):
    query = select(Carousel).where(Carousel.id == id)
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if not item:
        return error("轮播图不存在")
    return success(format_carousel(item))


@router.post("")
async def create_carousel(
    title: Optional[str] = Query(None),
    imageUrl: str = Query(...),
    linkUrl: Optional[str] = Query(None),
    sortOrder: Optional[int] = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    item = Carousel(
        title=title,
        image_url=imageUrl,
        link_url=linkUrl,
        sort_order=sortOrder,
    )
    db.add(item)
    await db.flush()
    return success(format_carousel(item))


@router.put("")
async def update_carousel(
    id: int = Query(...),
    title: Optional[str] = Query(None),
    imageUrl: Optional[str] = Query(None),
    linkUrl: Optional[str] = Query(None),
    sortOrder: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = select(Carousel).where(Carousel.id == id)
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if not item:
        return error("轮播图不存在")

    if title is not None:
        item.title = title
    if imageUrl is not None:
        item.image_url = imageUrl
    if linkUrl is not None:
        item.link_url = linkUrl
    if sortOrder is not None:
        item.sort_order = sortOrder
    if status is not None:
        item.status = status

    return success()


@router.delete("/{ids}")
async def delete_carousel(
    ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    id_list = [int(id) for id in ids.split(",")]
    stmt = delete(Carousel).where(Carousel.id.in_(id_list))
    await db.execute(stmt)
    return success()


@router.post("/export")
async def export_carousel(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """导出轮播图列表为 Excel"""
    query = select(Carousel).where(Carousel.status == "0").order_by(Carousel.sort_order.asc())
    result = await db.execute(query)
    items = list(result.scalars().all())

    rows = [{
        "id": i.id,
        "title": i.title or "",
        "imageUrl": i.image_url,
        "linkUrl": i.link_url or "",
        "sortOrder": i.sort_order,
        "status": "正常" if i.status == "0" else "停用",
        "createTime": i.create_time.isoformat() if i.create_time else "",
    } for i in items]

    headers = [
        {"key": "id", "label": "ID"},
        {"key": "title", "label": "标题"},
        {"key": "imageUrl", "label": "图片地址"},
        {"key": "linkUrl", "label": "链接地址"},
        {"key": "sortOrder", "label": "排序"},
        {"key": "status", "label": "状态"},
        {"key": "createTime", "label": "创建时间"},
    ]

    return export_to_excel(rows, headers, "carousel")
