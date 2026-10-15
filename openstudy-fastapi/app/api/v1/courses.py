"""
课程 API - 完整实现
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.core.security import get_current_user, is_admin_user
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
    """批量软删课程（`del_flag='2'`）

    ⚠️ **在这个端点之前 `current_user` 拿到手却一个字没用** —— 任何登录用户拿一串
    id 就能软删**别人的**课程（水平越权）。现在补上归属过滤：
      · 管理员：维持原行为（可删任意 id）；
      · 非管理员：只能删**自己的**行，一个都没命中就整体回 403。

    ⚠️ `Course.user_id` **可为 NULL**（全局课程，历史上由后台建、不属于任何用户）。
    SQL 里 NULL 参与 `=`/`!=` 的结果都是 NULL（既非真也非假），所以**绝不能**写成
    `Course.user_id != uid` —— 那样全局课程会被判成「不是我的」而拦下…或者反过来，
    写成 `or user_id is null` 就把它放行了。必须显式写「非空且等于我」。

    管理员判定用共享的 `core.security.is_admin_user`（`core/security.py:117`，最严那版：
    `roles` 含 `admin`；**刻意**不跟 `api/v1/ai_config.py` 那份更宽的走）——
    不再在文件里写第 4 份拷贝。
    """
    ids = [int(id) for id in course_ids.split(",")]

    if is_admin_user(current_user):
        stmt = update(Course).where(Course.course_id.in_(ids)).values(del_flag="2")
        await db.execute(stmt)
        return success()

    user_id = int(current_user.get("user_id") or 0)
    # ⚠️ WHERE 里特意**不加** `del_flag == '0'`：把已经软删过的自己的课程再删一次仍是
    #    「命中」（值还是 '2'），不该被误判成「无权删除他人课程」。
    stmt = (
        update(Course)
        .where(
            Course.course_id.in_(ids),
            Course.user_id.isnot(None),
            Course.user_id == user_id,
        )
        .values(del_flag="2")
    )
    result = await db.execute(stmt)
    if not (result.rowcount or 0):
        # 「不存在」与「不是你的」**回同一句**：分开说等于给攻击者一个存在性预言机
        # （拿一串 id 试一遍就能数出别人有多少课程）。
        return error("无权删除他人的课程", code=403)
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
