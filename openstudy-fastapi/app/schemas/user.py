"""
用户相关 Schema
"""

import re
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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


class ProfileUpdate(CamelModel):
    """当前登录用户修改个人资料（JSON body；字段均可选）"""

    nick_name: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=50)
    phonenumber: Optional[str] = Field(None, max_length=20)
    sex: Optional[str] = None

    @field_validator("nick_name")
    @classmethod
    def validate_nick_name(cls, value):
        if value is not None and not value.strip():
            raise ValueError("昵称不能为空")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        if value:
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
                raise ValueError("邮箱格式不正确")
        return value

    @field_validator("phonenumber")
    @classmethod
    def validate_phone(cls, value):
        # 只对非空值做宽容格式校验：存量用户可能有固话/分机号，
        # 强套 11 位手机号会把“改昵称/改邮箱”一起拦死。
        if value:
            if not re.match(r"^[0-9+\-() ]{5,20}$", value):
                raise ValueError("电话号码格式不正确")
        return value

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, value):
        # 兼容存量数据/前端未选择：空串视为“未设置”，允许清空。
        if value not in (None, "", "0", "1", "2"):
            raise ValueError("性别取值不合法")
        return value


class PasswordUpdate(CamelModel):
    """修改密码（JSON body，避免密码进入 URL/access log）"""

    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=20)
    confirm_password: Optional[str] = None

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value):
        if value == "123456":
            raise ValueError("新密码不能与初始密码相同")
        return value

    @model_validator(mode="after")
    def validate_confirm_password(self):
        if self.confirm_password is not None and self.new_password != self.confirm_password:
            raise ValueError("两次输入的密码不一致")
        return self


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
