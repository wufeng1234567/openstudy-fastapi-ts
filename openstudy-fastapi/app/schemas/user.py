"""
用户相关 Schema
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typing import Optional
from datetime import datetime


class CamelModel(BaseModel):
    """兼容若依前端 camelCase 入参；同时保留 snake_case 可用。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UserCreate(CamelModel):
    """创建用户"""
    user_name: str = Field(..., min_length=1, max_length=30)
    nick_name: str = Field(..., min_length=1, max_length=30)
    password: str = Field(..., min_length=5, max_length=20)
    email: Optional[str] = Field(None, max_length=50)
    phonenumber: Optional[str] = Field(None, max_length=11)
    sex: Optional[str] = Field("0")
    dept_id: Optional[int] = None
    role_ids: Optional[list] = None
    status: Optional[str] = Field("0")
    remark: Optional[str] = None


class UserUpdate(CamelModel):
    """更新用户"""
    user_id: int
    nick_name: Optional[str] = None
    email: Optional[str] = None
    phonenumber: Optional[str] = None
    sex: Optional[str] = None
    dept_id: Optional[int] = None
    role_ids: Optional[list] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class UserQuery(BaseModel):
    """用户查询"""
    user_name: Optional[str] = None
    phonenumber: Optional[str] = None
    status: Optional[str] = None
    dept_id: Optional[int] = None


class UserStatusUpdate(CamelModel):
    """修改用户状态"""
    user_id: int
    status: str


class ResetPasswordRequest(CamelModel):
    """重置密码"""
    user_id: int
    password: str = Field(..., min_length=5, max_length=20)
