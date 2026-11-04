"""后台监控：操作日志 / 登录日志 / 定时任务 / 调度日志。

前端页面早已存在（`views/monitor/operlog`、`logininfor`、`job`、`job/log`），
但 FastAPI 侧此前没有表和接口，所有请求都落到 catch_all 的假空态。
本文件提供真实 CRUD 与导出，菜单由 `deploy/db-init/30_monitor_tables.sql` 恢复显示。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error, paginate, success
from app.core.security import require_admin
from app.database import get_db
from app.models.monitor import SysJob, SysJobLog, SysLogininfor, SysOperLog
from app.services import job_scheduler
from app.utils.excel_util import export_to_excel

router = APIRouter(prefix="/monitor")


def _dt_text(value: Optional[datetime]) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def _parse_date(value: Optional[str], *, end: bool = False) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt + (timedelta(days=1) if end and fmt == "%Y-%m-%d" else timedelta(0))
        except ValueError:
            continue
    return None


def _date_range(request: Request) -> tuple[Optional[datetime], Optional[datetime]]:
    """兼容 axios 的 `params[beginTime]` 序列化，也兼容直接 `beginTime`。"""
    q = request.query_params
    begin = q.get("params[beginTime]") or q.get("beginTime")
    end = q.get("params[endTime]") or q.get("endTime")
    return _parse_date(begin), _parse_date(end, end=True)


def _order(query, column, is_asc: Optional[str]):
    desc = (is_asc or "descending") == "descending"
    return query.order_by(column.desc() if desc else column.asc())


def _oper_row(row: SysOperLog) -> Dict[str, Any]:
    return {
        "operId": int(row.oper_id),
        "title": row.title,
        "businessType": int(row.business_type or 0),
        "method": row.method,
        "requestMethod": row.request_method,
        "operatorType": int(row.operator_type or 0),
        "operName": row.oper_name,
        "deptName": row.dept_name,
        "operUrl": row.oper_url,
        "operIp": row.oper_ip,
        "operLocation": row.oper_location,
        "operParam": row.oper_param,
        "jsonResult": row.json_result,
        "status": int(row.status or 0),
        "errorMsg": row.error_msg,
        "operTime": _dt_text(row.oper_time),
        "costTime": int(row.cost_time or 0),
    }


@router.get("/operlog/list")
async def list_oper_log(
    request: Request,
    title: Optional[str] = Query(None),
    operName: Optional[str] = Query(None),
    operIp: Optional[str] = Query(None),
    businessType: Optional[int] = Query(None),
    status: Optional[int] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    orderByColumn: Optional[str] = Query(None),
    isAsc: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    query = select(SysOperLog)
    if title:
        query = query.where(SysOperLog.title.ilike(f"%{title}%"))
    if operName:
        query = query.where(SysOperLog.oper_name.ilike(f"%{operName}%"))
    if operIp:
        query = query.where(SysOperLog.oper_ip.ilike(f"%{operIp}%"))
    if businessType is not None:
        query = query.where(SysOperLog.business_type == int(businessType))
    if status is not None:
        query = query.where(SysOperLog.status == int(status))
    begin, end = _date_range(request)
    if begin:
        query = query.where(SysOperLog.oper_time >= begin)
    if end:
        query = query.where(SysOperLog.oper_time < end)

    total = int(await db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    sort_map = {
        "operTime": SysOperLog.oper_time,
        "costTime": SysOperLog.cost_time,
        "operName": SysOperLog.oper_name,
    }
    query = _order(query, sort_map.get(orderByColumn or "", SysOperLog.oper_time), isAsc)
    rows = (
        await db.execute(query.offset((pageNum - 1) * pageSize).limit(pageSize))
    ).scalars().all()
    return paginate(total, [_oper_row(r) for r in rows])


@router.delete("/operlog/clean")
async def clean_oper_log(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    result = await db.execute(delete(SysOperLog))
    return success({"deleted": int(result.rowcount or 0)}, "清空成功")


@router.delete("/operlog/{oper_ids}")
async def delete_oper_log(
    oper_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    ids = [int(x) for x in oper_ids.split(",") if x.strip().isdigit()]
    if not ids:
        return error("日志编号无效", code=400)
    await db.execute(delete(SysOperLog).where(SysOperLog.oper_id.in_(ids)))
    return success()


@router.get("/operlog/export")
async def export_oper_log(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    query = select(SysOperLog).order_by(SysOperLog.oper_time.desc()).limit(5000)
    rows = (await db.execute(query)).scalars().all()
    data = [_oper_row(r) for r in rows]
    return export_to_excel(
        data,
        [
            {"key": "operId", "label": "日志编号"},
            {"key": "title", "label": "系统模块"},
            {"key": "businessType", "label": "操作类型"},
            {"key": "operName", "label": "操作人员"},
            {"key": "operIp", "label": "操作地址"},
            {"key": "status", "label": "操作状态"},
            {"key": "operTime", "label": "操作时间"},
            {"key": "costTime", "label": "消耗时间(ms)"},
        ],
        "operlog",
    )


# ---------------------------------------------------------------- 登录日志

def _login_row(row: SysLogininfor) -> Dict[str, Any]:
    return {
        "infoId": int(row.info_id),
        "userName": row.user_name,
        "ipaddr": row.ipaddr,
        "loginLocation": row.login_location,
        "browser": row.browser,
        "os": row.os,
        "status": int(row.status or 0),
        "msg": row.msg,
        "loginTime": _dt_text(row.login_time),
    }


@router.get("/logininfor/list")
async def list_logininfor(
    request: Request,
    userName: Optional[str] = Query(None),
    ipaddr: Optional[str] = Query(None),
    status: Optional[int] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    orderByColumn: Optional[str] = Query(None),
    isAsc: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    query = select(SysLogininfor)
    if userName:
        query = query.where(SysLogininfor.user_name.ilike(f"%{userName}%"))
    if ipaddr:
        query = query.where(SysLogininfor.ipaddr.ilike(f"%{ipaddr}%"))
    if status is not None:
        query = query.where(SysLogininfor.status == int(status))
    begin, end = _date_range(request)
    if begin:
        query = query.where(SysLogininfor.login_time >= begin)
    if end:
        query = query.where(SysLogininfor.login_time < end)

    total = int(await db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    sort_map = {
        "loginTime": SysLogininfor.login_time,
        "userName": SysLogininfor.user_name,
    }
    query = _order(query, sort_map.get(orderByColumn or "", SysLogininfor.login_time), isAsc)
    rows = (
        await db.execute(query.offset((pageNum - 1) * pageSize).limit(pageSize))
    ).scalars().all()
    return paginate(total, [_login_row(r) for r in rows])


@router.delete("/logininfor/clean")
async def clean_logininfor(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    result = await db.execute(delete(SysLogininfor))
    return success({"deleted": int(result.rowcount or 0)}, "清空成功")


@router.delete("/logininfor/{info_ids}")
async def delete_logininfor(
    info_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    ids = [int(x) for x in info_ids.split(",") if x.strip().isdigit()]
    if not ids:
        return error("日志编号无效", code=400)
    await db.execute(delete(SysLogininfor).where(SysLogininfor.info_id.in_(ids)))
    return success()


@router.get("/logininfor/unlock/{user_name}")
async def unlock_logininfor(
    user_name: str,
    current_user: dict = Depends(require_admin),
):
    """本系统没有账号锁定表；保留该入口并明确回执，避免前端误以为操作成功。"""
    return success({"userName": user_name, "unlocked": False}, f"用户 {user_name} 当前未被锁定")


@router.get("/logininfor/export")
async def export_logininfor(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    rows = (
        await db.execute(
            select(SysLogininfor).order_by(SysLogininfor.login_time.desc()).limit(5000)
        )
    ).scalars().all()
    return export_to_excel(
        [_login_row(r) for r in rows],
        [
            {"key": "infoId", "label": "访问编号"},
            {"key": "userName", "label": "用户名称"},
            {"key": "ipaddr", "label": "地址"},
            {"key": "loginLocation", "label": "登录地点"},
            {"key": "os", "label": "操作系统"},
            {"key": "browser", "label": "浏览器"},
            {"key": "status", "label": "登录状态"},
            {"key": "msg", "label": "描述"},
            {"key": "loginTime", "label": "访问时间"},
        ],
        "logininfor",
    )


# ---------------------------------------------------------------- 定时任务

class JobBody(BaseModel):
    jobId: Optional[int] = None
    jobName: str = Field(..., max_length=64)
    jobGroup: str = Field(default="DEFAULT", max_length=64)
    invokeTarget: str = Field(..., max_length=255)
    cronExpression: str = Field(..., max_length=255)
    misfirePolicy: str = "1"
    concurrent: str = "1"
    status: str = "0"
    remark: Optional[str] = ""


class JobStatusBody(BaseModel):
    jobId: int
    status: str


class JobRunBody(BaseModel):
    jobId: int
    jobGroup: Optional[str] = None


def _job_row(job: SysJob) -> Dict[str, Any]:
    return {
        "jobId": int(job.job_id),
        "jobName": job.job_name,
        "jobGroup": job.job_group,
        "invokeTarget": job.invoke_target,
        "cronExpression": job.cron_expression,
        "misfirePolicy": job.misfire_policy,
        "concurrent": job.concurrent,
        "status": job.status,
        "remark": job.remark,
        "createTime": _dt_text(job.create_time),
        "updateTime": _dt_text(job.update_time),
        "nextValidTime": (
            job_scheduler.next_run_time(job.cron_expression)
            if job.status == "0"
            else ""
        ),
    }


def _validate_job(body: JobBody) -> Optional[str]:
    if body.invokeTarget not in job_scheduler.available_targets():
        return (
            f"不支持的调用目标：{body.invokeTarget}；"
            f"可用：{', '.join(job_scheduler.available_targets())}"
        )
    if not job_scheduler.validate_cron(body.cronExpression):
        return "cron 表达式不合法（支持 5 段标准格式或若依 6 段格式）"
    if body.status not in ("0", "1"):
        return "状态只能是 0（正常）或 1（暂停）"
    return None


@router.get("/job/list")
async def list_jobs(
    jobName: Optional[str] = Query(None),
    jobGroup: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    query = select(SysJob)
    if jobName:
        query = query.where(SysJob.job_name.ilike(f"%{jobName}%"))
    if jobGroup:
        query = query.where(SysJob.job_group == jobGroup)
    if status:
        query = query.where(SysJob.status == status)
    total = int(await db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = (
        await db.execute(
            query.order_by(SysJob.job_id.asc())
            .offset((pageNum - 1) * pageSize)
            .limit(pageSize)
        )
    ).scalars().all()
    return paginate(total, [_job_row(j) for j in rows])


@router.get("/job/export")
async def export_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """导出必须注册在 `/job/{job_id}` 之前，否则会被当成 job_id=export 解析成 422。"""
    rows = (await db.execute(select(SysJob).order_by(SysJob.job_id))).scalars().all()
    return export_to_excel(
        [_job_row(j) for j in rows],
        [
            {"key": "jobId", "label": "任务编号"},
            {"key": "jobName", "label": "任务名称"},
            {"key": "jobGroup", "label": "任务组名"},
            {"key": "invokeTarget", "label": "调用目标字符串"},
            {"key": "cronExpression", "label": "cron执行表达式"},
            {"key": "status", "label": "状态"},
            {"key": "createTime", "label": "创建时间"},
        ],
        "job",
    )


@router.get("/job/{job_id}")
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    job = await db.get(SysJob, job_id)
    if not job:
        return error("任务不存在", code=404)
    return success(_job_row(job))


@router.post("/job")
async def create_job(
    body: JobBody,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    reason = _validate_job(body)
    if reason:
        return error(reason, code=400)
    exists = await db.scalar(select(SysJob.job_id).where(SysJob.job_name == body.jobName))
    if exists:
        return error("任务名称已存在", code=400)
    job = SysJob(
        job_name=body.jobName.strip(),
        job_group=body.jobGroup.strip() or "DEFAULT",
        invoke_target=body.invokeTarget.strip(),
        cron_expression=body.cronExpression.strip(),
        misfire_policy=body.misfirePolicy,
        concurrent=body.concurrent,
        status=body.status,
        remark=(body.remark or "")[:500],
        create_time=datetime.now(),
    )
    db.add(job)
    await db.flush()
    return success(_job_row(job), "新增成功")


@router.put("/job")
async def update_job(
    body: JobBody,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    if not body.jobId:
        return error("缺少任务编号", code=400)
    reason = _validate_job(body)
    if reason:
        return error(reason, code=400)
    job = await db.get(SysJob, int(body.jobId))
    if not job:
        return error("任务不存在", code=404)
    exists = await db.scalar(
        select(SysJob.job_id).where(
            SysJob.job_name == body.jobName, SysJob.job_id != int(body.jobId)
        )
    )
    if exists:
        return error("任务名称已存在", code=400)
    job.job_name = body.jobName.strip()
    job.job_group = body.jobGroup.strip() or "DEFAULT"
    job.invoke_target = body.invokeTarget.strip()
    job.cron_expression = body.cronExpression.strip()
    job.misfire_policy = body.misfirePolicy
    job.concurrent = body.concurrent
    job.status = body.status
    job.remark = (body.remark or "")[:500]
    job.update_time = datetime.now()
    await db.flush()
    return success(_job_row(job), "修改成功")


@router.put("/job/changeStatus")
async def change_job_status(
    body: JobStatusBody,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    job = await db.get(SysJob, int(body.jobId))
    if not job:
        return error("任务不存在", code=404)
    if body.status not in ("0", "1"):
        return error("状态只能是 0（正常）或 1（暂停）", code=400)
    job.status = body.status
    job.update_time = datetime.now()
    await db.flush()
    return success(_job_row(job), "状态更新成功")


@router.put("/job/run")
async def run_job(
    body: JobRunBody,
    current_user: dict = Depends(require_admin),
):
    result = await job_scheduler.run_job(int(body.jobId), manual=True)
    if not result.get("ok"):
        return error(str(result.get("message") or "执行失败"), code=400)
    return success(result, "执行成功")


@router.delete("/job/{job_ids}")
async def delete_job(
    job_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    ids = [int(x) for x in job_ids.split(",") if x.strip().isdigit()]
    if not ids:
        return error("任务编号无效", code=400)
    await db.execute(delete(SysJob).where(SysJob.job_id.in_(ids)))
    return success()


# ---------------------------------------------------------------- 调度日志

def _job_log_row(row: SysJobLog) -> Dict[str, Any]:
    return {
        "jobLogId": int(row.job_log_id),
        "jobName": row.job_name,
        "jobGroup": row.job_group,
        "invokeTarget": row.invoke_target,
        "jobMessage": row.job_message,
        "status": int(row.status or 0),
        "exceptionInfo": row.exception_info,
        "createTime": _dt_text(row.create_time),
    }


@router.get("/jobLog/list")
async def list_job_log(
    request: Request,
    jobName: Optional[str] = Query(None),
    jobGroup: Optional[str] = Query(None),
    status: Optional[int] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    query = select(SysJobLog)
    if jobName:
        query = query.where(SysJobLog.job_name.ilike(f"%{jobName}%"))
    if jobGroup:
        query = query.where(SysJobLog.job_group == jobGroup)
    if status is not None:
        query = query.where(SysJobLog.status == int(status))
    begin, end = _date_range(request)
    if begin:
        query = query.where(SysJobLog.create_time >= begin)
    if end:
        query = query.where(SysJobLog.create_time < end)
    total = int(await db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = (
        await db.execute(
            query.order_by(SysJobLog.create_time.desc())
            .offset((pageNum - 1) * pageSize)
            .limit(pageSize)
        )
    ).scalars().all()
    return paginate(total, [_job_log_row(r) for r in rows])


@router.delete("/jobLog/clean")
async def clean_job_log(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    result = await db.execute(delete(SysJobLog))
    return success({"deleted": int(result.rowcount or 0)}, "清空成功")


@router.delete("/jobLog/{job_log_ids}")
async def delete_job_log(
    job_log_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    ids = [int(x) for x in job_log_ids.split(",") if x.strip().isdigit()]
    if not ids:
        return error("日志编号无效", code=400)
    await db.execute(delete(SysJobLog).where(SysJobLog.job_log_id.in_(ids)))
    return success()


@router.get("/jobLog/export")
async def export_job_log(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    rows = (
        await db.execute(
            select(SysJobLog).order_by(SysJobLog.create_time.desc()).limit(5000)
        )
    ).scalars().all()
    return export_to_excel(
        [_job_log_row(r) for r in rows],
        [
            {"key": "jobLogId", "label": "日志编号"},
            {"key": "jobName", "label": "任务名称"},
            {"key": "jobGroup", "label": "任务组名"},
            {"key": "invokeTarget", "label": "调用目标字符串"},
            {"key": "jobMessage", "label": "日志信息"},
            {"key": "status", "label": "执行状态"},
            {"key": "createTime", "label": "执行时间"},
        ],
        "job_log",
    )
