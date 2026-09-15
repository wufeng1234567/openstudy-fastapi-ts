"""
角色模型
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import BigInteger, String, Integer, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SysRole(Base):
    """角色表"""
    __tablename__ = "sys_role"

    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_name: Mapped[str] = mapped_column(String(30), nullable=False)
    role_key: Mapped[str] = mapped_column(String(100), nullable=False)
    role_sort: Mapped[int] = mapped_column(Integer, nullable=False)
    data_scope: Mapped[str] = mapped_column(String(1), default="1")
    menu_check_strictly: Mapped[bool] = mapped_column(Boolean, default=True)
    dept_check_strictly: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(1), nullable=False, default="0")
    del_flag: Mapped[str] = mapped_column(String(1), default="0")
    create_by: Mapped[Optional[str]] = mapped_column(String(64), default="")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    update_by: Mapped[Optional[str]] = mapped_column(String(64), default="")
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(String(500))

    # 关系
    users: Mapped[List["SysUser"]] = relationship(
        secondary="sys_user_role",
        back_populates="roles",
        lazy="selectin",
    )
    menus: Mapped[List["SysMenu"]] = relationship(
        secondary="sys_role_menu",
        back_populates="roles",
        lazy="selectin",
    )


class SysRoleMenu(Base):
    """角色菜单关联表"""
    __tablename__ = "sys_role_menu"

    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_role.role_id"), primary_key=True)
    menu_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_menu.menu_id"), primary_key=True)
