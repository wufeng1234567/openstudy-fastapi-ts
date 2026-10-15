"""
笔记相关 Schema
"""

from pydantic import BaseModel, Field
from typing import Optional


class NoteCreate(BaseModel):
    """创建笔记"""
    title: str = Field(..., min_length=1, max_length=255)
    content: Optional[str] = None
    category_id: Optional[int] = None
    cover_image: Optional[str] = None
    is_public: Optional[str] = "0"
    status: Optional[str] = "0"


class NoteUpdate(BaseModel):
    """更新笔记"""
    note_id: int
    title: Optional[str] = None
    content: Optional[str] = None
    category_id: Optional[int] = None
    cover_image: Optional[str] = None
    is_public: Optional[str] = None
    status: Optional[str] = None


class NoteQuery(BaseModel):
    """笔记查询"""
    title: Optional[str] = None
    category_id: Optional[int] = None
    is_public: Optional[str] = None
    status: Optional[str] = None


class NoteCategoryCreate(BaseModel):
    """创建笔记分类"""
    name: str = Field(..., min_length=1, max_length=100)
    order_num: Optional[int] = 0


class NoteCategoryUpdate(BaseModel):
    """更新笔记分类"""
    id: int
    name: Optional[str] = None
    order_num: Optional[int] = None
