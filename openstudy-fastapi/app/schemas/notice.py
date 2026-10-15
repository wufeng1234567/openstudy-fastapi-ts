"""
通知公告相关 Schema
"""

from pydantic import BaseModel, Field
from typing import Optional


class NoticeCreate(BaseModel):
    """创建公告"""
    notice_title: str = Field(..., min_length=1, max_length=50)
    notice_type: str = Field(..., description="公告类型: 1通知 2公告")
    notice_content: Optional[str] = None
    status: Optional[str] = "0"
    remark: Optional[str] = None


class NoticeUpdate(BaseModel):
    """更新公告"""
    notice_id: int
    notice_title: Optional[str] = None
    notice_type: Optional[str] = None
    notice_content: Optional[str] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class NoticeQuery(BaseModel):
    """公告查询"""
    notice_title: Optional[str] = None
    notice_type: Optional[str] = None
    status: Optional[str] = None
