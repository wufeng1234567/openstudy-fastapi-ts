"""
菜单模型
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import BigInteger, String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SysMenu(Base):
    """菜单表"""
    __tablename__ = "sys_menu"

    menu_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    menu_name: Mapped[str] = mapped_column(String(50), nullable=False)
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0)
    order_num: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[Optional[str]] = mapped_column(String(200), default="")
    component: Mapped[Optional[str]] = mapped_column(String(255))
    query: Mapped[Optional[str]] = mapped_column(String(255))
    is_frame: Mapped[int] = mapped_column(Integer, default=1)
    is_cache: Mapped[int] = mapped_column(Integer, default=0)
    menu_type: Mapped[str] = mapped_column(String(1), default="")
    visible: Mapped[str] = mapped_column(String(1), default="0")
    status: Mapped[str] = mapped_column(String(1), default="0")
    perms: Mapped[Optional[str]] = mapped_column(String(100))
    icon: Mapped[str] = mapped_column(String(100), default="#")
    create_by: Mapped[Optional[str]] = mapped_column(String(64), default="")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    update_by: Mapped[Optional[str]] = mapped_column(String(64), default="")
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(String(500))

    # 关系
    roles: Mapped[List["SysRole"]] = relationship(
        secondary="sys_role_menu",
        back_populates="menus",
        lazy="selectin",
    )
    children: Mapped[List["SysMenu"]] = relationship(
        back_populates="parent",
        lazy="selectin",
        foreign_keys="SysMenu.parent_id",
        primaryjoin="SysMenu.menu_id == SysMenu.parent_id",
    )
    parent: Mapped[Optional["SysMenu"]] = relationship(
        back_populates="children",
        remote_side="SysMenu.menu_id",
        lazy="selectin",
        foreign_keys="SysMenu.parent_id",
        primaryjoin="SysMenu.parent_id == SysMenu.menu_id",
    )
