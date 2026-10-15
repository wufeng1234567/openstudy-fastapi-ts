"""
仪表盘 API
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success
from app.models.user import SysUser
from app.models.question import QuestionBank, QuestionMain
from app.models.note import Note

router = APIRouter(prefix="/system/dashboard")


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取仪表盘统计数据"""
    user_count = await db.scalar(select(func.count()).where(SysUser.del_flag == "0"))
    bank_count = await db.scalar(select(func.count()).where(QuestionBank.status == "0"))
    question_count = await db.scalar(select(func.count()).where(QuestionMain.status == "0"))
    note_count = await db.scalar(select(func.count()).where(Note.del_flag == "0"))

    # 分类统计:按 subject 分组统计题库数
    category_query = select(
        QuestionBank.subject,
        func.count(QuestionBank.id).label("count"),
    ).where(QuestionBank.status == "0").group_by(QuestionBank.subject)
    category_result = await db.execute(category_query)
    category_stats = [
        {"name": row.subject or "未分类", "value": row.count}
        for row in category_result.all()
    ]

    # 用户增长趋势:最近7天每天新增用户
    seven_days_ago = datetime.now() - timedelta(days=7)
    growth_query = select(
        func.date(SysUser.create_time).label("date"),
        func.count(SysUser.user_id).label("count"),
    ).where(
        SysUser.del_flag == "0",
        SysUser.create_time >= seven_days_ago,
    ).group_by(func.date(SysUser.create_time)).order_by(func.date(SysUser.create_time))
    growth_result = await db.execute(growth_query)
    user_growth = [
        {"date": str(row.date), "count": row.count}
        for row in growth_result.all()
    ]

    return success({
        "userCount": user_count or 0,
        "bankCount": bank_count or 0,
        "questionBankCount": bank_count or 0,  # 向后兼容前端字段命名
        "questionCount": question_count or 0,
        "noteCount": note_count or 0,
        "categoryStats": category_stats,
        "userGrowth": user_growth,
    })


@router.get("/recent")
async def get_recent_activities(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取最近活动

    合并最近题库创建、题目创建、笔记发布,按时间倒序取前10条。
    """
    activities = []

    # 最近的题库创建
    bank_query = select(
        QuestionBank.id,
        QuestionBank.bank_name,
        QuestionBank.subject,
        QuestionBank.create_time,
    ).where(QuestionBank.status == "0").order_by(
        QuestionBank.create_time.desc()
    ).limit(10)
    bank_result = await db.execute(bank_query)
    for row in bank_result.all():
        activities.append({
            "type": "bank",
            "id": row.id,
            "title": row.bank_name,
            "subject": row.subject or "未分类",
            "createTime": row.create_time.isoformat() if row.create_time else None,
            "time": row.create_time,
        })

    # 最近的题目创建
    question_query = select(
        QuestionMain.id,
        QuestionMain.question_text,
        QuestionMain.create_time,
    ).where(QuestionMain.status == "0").order_by(
        QuestionMain.create_time.desc()
    ).limit(10)
    question_result = await db.execute(question_query)
    for row in question_result.all():
        text = (row.question_text or "")[:60]
        activities.append({
            "type": "question",
            "id": row.id,
            "title": text,
            "createTime": row.create_time.isoformat() if row.create_time else None,
            "time": row.create_time,
        })

    # 最近的笔记发布
    note_query = select(
        Note.note_id,
        Note.title,
        Note.create_time,
    ).where(Note.del_flag == "0").order_by(
        Note.create_time.desc()
    ).limit(10)
    note_result = await db.execute(note_query)
    for row in note_result.all():
        activities.append({
            "type": "note",
            "id": row.note_id,
            "title": row.title,
            "createTime": row.create_time.isoformat() if row.create_time else None,
            "time": row.create_time,
        })

    # 合并按时间倒序,取前10条
    activities.sort(key=lambda x: x.get("time") or datetime.min, reverse=True)
    activities = activities[:10]
    # 移除内部排序用的 time 字段
    for a in activities:
        a.pop("time", None)

    return success(activities)
