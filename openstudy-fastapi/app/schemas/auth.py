"""
认证相关 Schema
"""

from pydantic import BaseModel, Field
from typing import Optional


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=1, max_length=30, description="用户名")
    password: str = Field(..., min_length=1, max_length=100, description="密码")
    code: Optional[str] = Field(None, description="验证码")
    uuid: Optional[str] = Field(None, description="验证码UUID")


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=1, max_length=30, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    nick_name: Optional[str] = Field(None, max_length=30, description="昵称")


class LoginResponse(BaseModel):
    """登录响应"""
    token: str


class UserInfoResponse(BaseModel):
    """用户信息响应"""
    user: dict
    roles: list
    permissions: list
