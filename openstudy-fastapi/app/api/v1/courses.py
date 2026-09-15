"""
课程 API - 完整实现
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, paginate, error
from app.models.courses import Course
from app.utils.excel_util import export_to_excel
from datetime import datetime

router = APIRouter(prefix="/courses/courses")


def format_course(course):
    return {
        "courseId": course.course_id,
        "courseName": course.course_name,
        "courseDescription": course.course_description,
        "coverImage": course.cover_image,
        "userId": course.user_id,
        "category": course.category,
        "status": course.status,
        "createTime": course.create_time.isoformat() if course.create_time else None,
        "updateTime": course.update_time.isoformat() if course.update_time else None,
    }


@router.get("/list")
async def list_courses(
    courseName: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = select(Course).where(Course.del_flag == "0")
    if courseName:
        query = query.where(Course.course_name.ilike(f"%{courseName}%"))
    if category:
        query = query.where(Course.category == category)
    if status:
        query = query.where(Course.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(Course.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    courses = list(result.scalars().all())

    return paginate(total, [format_course(c) for c in courses])


@router.get("/all")
async def list_all_courses(
    db: AsyncSession = Depends(get_db),
):
    query = select(Course).where(Course.del_flag == "0").order_by(Course.create_time.desc())
    result = await db.execute(query)
    courses = list(result.scalars().all())
    return success([format_course(c) for c in courses])


@router.get("/{course_id}")
async def get_course(
    course_id: int,
    db: AsyncSession = Depends(get_db),
):
    query = select(Course).where(Course.course_id == course_id, Course.del_flag == "0")
    result = await db.execute(query)
    course = result.scalar_one_or_none()
    if not course:
        return error("课程不存在")
    return success(format_course(course))


@router.post("")
async def create_course(
    courseName: str = Query(...),
    courseDescription: Optional[str] = Query(None),
    coverImage: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user.get("user_id")
    course = Course(
        course_name=courseName,
        course_description=courseDescription,
        cover_image=coverImage,
        category=category,
        user_id=user_id,
    )
    db.add(course)
    await db.flush()
    return success(format_course(course))


@router.put("")
async def update_course(
    courseId: int = Query(...),
    courseName: Optional[str] = Query(None),
    courseDescription: Optional[str] = Query(None),
    coverImage: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = select(Course).where(Course.course_id == courseId, Course.del_flag == "0")
    result = await db.execute(query)
    course = result.scalar_one_or_none()
    if not course:
        return error("课程不存在")

    if courseName is not None:
        course.course_name = courseName
    if courseDescription is not None:
        course.course_description = courseDescription
    if coverImage is not None:
        course.cover_image = coverImage
    if category is not None:
        course.category = category
    if status is not None:
        course.status = status

    return success()


@router.delete("/{course_ids}")
async def delete_courses(
    course_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ids = [int(id) for id in course_ids.split(",")]
    stmt = update(Course).where(Course.course_id.in_(ids)).values(del_flag="2")
    await db.execute(stmt)
    return success()


@router.post("/export")
async def export_courses(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """导出课程列表为 Excel"""
    query = select(Course).where(Course.del_flag == "0").order_by(Course.create_time.desc())
    result = await db.execute(query)
    courses = list(result.scalars().all())

    rows = [{
        "courseId": c.course_id,
        "courseName": c.course_name,
        "courseDescription": c.course_description or "",
        "category": c.category or "",
        "userId": c.user_id,
        "status": "正常" if c.status == "0" else "停用",
        "createTime": c.create_time.isoformat() if c.create_time else "",
    } for c in courses]

    headers = [
        {"key": "courseId", "label": "课程ID"},
        {"key": "courseName", "label": "课程名称"},
        {"key": "courseDescription", "label": "课程描述"},
        {"key": "category", "label": "分类"},
        {"key": "userId", "label": "创建用户ID"},
        {"key": "status", "label": "状态"},
        {"key": "createTime", "label": "创建时间"},
    ]

    return export_to_excel(rows, headers, "courses")
