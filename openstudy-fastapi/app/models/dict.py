"""系统字典类型 / 字典数据（后台字典管理持久化）。

原先后台字典只是 `system.py` 里的两个进程内 list/dict，服务重启后新增项丢失。
这两张表只服务后台字典配置，字段与若依 `sys_dict_type` / `sys_dict_data` 对齐。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SysDictType(Base):
    __tablename__ = "sys_dict_type"

    dict_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dict_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dict_type: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(1), default="0")
    create_by: Mapped[Optional[str]] = mapped_column(String(64), default="")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.now)
    update_by: Mapped[Optional[str]] = mapped_column(String(64), default="")
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(String(500))


class SysDictData(Base):
    __tablename__ = "sys_dict_data"

    dict_code: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dict_sort: Mapped[int] = mapped_column(Integer, default=0)
    dict_label: Mapped[str] = mapped_column(String(100), nullable=False)
    dict_value: Mapped[str] = mapped_column(String(100), nullable=False)
    dict_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    css_class: Mapped[Optional[str]] = mapped_column(String(100), default="")
    list_class: Mapped[Optional[str]] = mapped_column(String(100), default="")
    is_default: Mapped[str] = mapped_column(String(1), default="N")
    status: Mapped[str] = mapped_column(String(1), default="0")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.now)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(String(500))
