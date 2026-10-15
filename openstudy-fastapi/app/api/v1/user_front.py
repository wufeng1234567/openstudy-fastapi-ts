"""
前台用户 API
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, paginate
from app.repositories.user_repo import UserRepository

router = APIRouter(prefix="/system/user")


@router.get("/frontList")
async def front_list_users(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """前台用户列表"""
    return paginate(0, [])


@router.get("/front/{user_id}")
async def get_front_user_info(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取前台用户信息"""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)

    if not user:
        return error("用户不存在")

    return success({
        "userId": user.user_id,
        "userName": user.user_name,
        "nickName": user.nick_name,
        "email": user.email,
        "phonenumber": user.phonenumber,
        "sex": user.sex,
        "avatar": user.avatar,
        "status": user.status,
    })
