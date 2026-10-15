"""
用户模型
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import BigInteger, String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SysUser(Base):
    """用户表"""
    __tablename__ = "sys_user"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    nick_name: Mapped[str] = mapped_column(String(30), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(50), default="")
    phonenumber: Mapped[Optional[str]] = mapped_column(String(11), default="")
    sex: Mapped[str] = mapped_column(String(1), default="0")
    avatar: Mapped[Optional[str]] = mapped_column(String(500), default="")
    password: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(1), default="0")
    del_flag: Mapped[str] = mapped_column(String(1), default="0")
    login_ip: Mapped[Optional[str]] = mapped_column(String(128), default="")
    login_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    dept_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("sys_dept.dept_id"))
    create_by: Mapped[Optional[str]] = mapped_column(String(64), default="")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    update_by: Mapped[Optional[str]] = mapped_column(String(64), default="")
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(String(500))

    # 关系
    roles: Mapped[List["SysRole"]] = relationship(
        secondary="sys_user_role",
        back_populates="users",
        lazy="selectin",
    )
    dept: Mapped[Optional["SysDept"]] = relationship(back_populates="users", lazy="selectin")


class SysUserRole(Base):
    """用户角色关联表"""
    __tablename__ = "sys_user_role"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_role.role_id"), primary_key=True)


class SysDept(Base):
    """部门表"""
    __tablename__ = "sys_dept"

    dept_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0)
    ancestors: Mapped[Optional[str]] = mapped_column(String(500), default="")
    dept_name: Mapped[str] = mapped_column(String(30), default="")
    order_num: Mapped[int] = mapped_column(Integer, default=0)
    leader: Mapped[Optional[str]] = mapped_column(String(20))
    phone: Mapped[Optional[str]] = mapped_column(String(11))
    email: Mapped[Optional[str]] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(1), default="0")
    del_flag: Mapped[str] = mapped_column(String(1), default="0")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 关系
    users: Mapped[List["SysUser"]] = relationship(back_populates="dept")
