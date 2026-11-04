"""后台监控：操作日志 / 登录日志 / 定时任务 / 调度日志。

对应前端已有的 `views/monitor/operlog`、`logininfor`、`job`、`job/log` 页面。
此前 FastAPI 侧没有这四张表，菜单被隐藏；2026-11-04 补齐真实持久化。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SysOperLog(Base):
    """操作日志（后台写操作自动记录）。"""

    __tablename__ = "sys_oper_log"

    oper_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(50), default="")
    business_type: Mapped[int] = mapped_column(Integer, default=0)
    method: Mapped[str] = mapped_column(String(255), default="")
    request_method: Mapped[str] = mapped_column(String(10), default="")
    operator_type: Mapped[int] = mapped_column(Integer, default=0)
    oper_name: Mapped[str] = mapped_column(String(50), default="")
    dept_name: Mapped[str] = mapped_column(String(50), default="")
    oper_url: Mapped[str] = mapped_column(String(255), default="")
    oper_ip: Mapped[str] = mapped_column(String(128), default="")
    oper_location: Mapped[str] = mapped_column(String(255), default="")
    oper_param: Mapped[Optional[str]] = mapped_column(Text)
    json_result: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[Optional[str]] = mapped_column(Text)
    oper_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    cost_time: Mapped[int] = mapped_column(BigInteger, default=0)


class SysLogininfor(Base):
    """登录日志（登录成功/失败/退出）。"""

    __tablename__ = "sys_logininfor"

    info_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(50), default="", index=True)
    ipaddr: Mapped[str] = mapped_column(String(128), default="")
    login_location: Mapped[str] = mapped_column(String(255), default="")
    browser: Mapped[str] = mapped_column(String(50), default="")
    os: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[int] = mapped_column(Integer, default=0)
    msg: Mapped[str] = mapped_column(String(255), default="")
    login_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class SysJob(Base):
    """定时任务定义。"""

    __tablename__ = "sys_job"

    job_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    job_group: Mapped[str] = mapped_column(String(64), default="DEFAULT")
    invoke_target: Mapped[str] = mapped_column(String(255), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(255), nullable=False)
    misfire_policy: Mapped[str] = mapped_column(String(1), default="1")
    concurrent: Mapped[str] = mapped_column(String(1), default="1")
    status: Mapped[str] = mapped_column(String(1), default="0", index=True)
    remark: Mapped[Optional[str]] = mapped_column(String(500), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class SysJobLog(Base):
    """定时任务每次执行的调度日志。"""

    __tablename__ = "sys_job_log"

    job_log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(64), default="", index=True)
    job_group: Mapped[str] = mapped_column(String(64), default="")
    invoke_target: Mapped[str] = mapped_column(String(255), default="")
    job_message: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[int] = mapped_column(Integer, default=0)
    exception_info: Mapped[Optional[str]] = mapped_column(Text)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
