"""轻量定时任务调度器（2026-11-04）。

为什么不用 APScheduler：
- 需求只有「后台配置 cron → 到点执行一个已知任务 → 记一条调度日志」；
- 引入 APScheduler 会多一个运行状态源（内存 jobstore 与 DB 不一致、重启丢任务），
  这里直接以 `sys_job` 表为唯一事实源，每 20 秒扫一次，逻辑可读、可测试。

支持的调用目标（`invoke_target`，白名单，拒绝任意代码执行）：
- practiceSessionCleanup     清理超过 2 小时未交卷的练习会话
- documentPipelineRecovery   回收卡在「解析中」的文档（服务重启/异常）
- dictCacheRefresh           从数据库重新加载字典缓存
- logCleanup                 清理 90 天前的操作/登录日志与 30 天前的调度日志

cron 表达式兼容若依/Quartz 的 6 段格式（秒 分 时 日 月 周），也兼容标准 5 段；
星期按 Quartz 口径：1=周日 … 7=周六，0 也按周日处理。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional, Set

from loguru import logger
from sqlalchemy import delete, select, update

from app.database import async_session_factory
from app.models.monitor import SysJob, SysJobLog

_CRON_ALIASES = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 1",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}


def _normalize_cron(expression: str) -> str:
    expr = (expression or "").strip()
    if not expr:
        raise ValueError("cron 表达式不能为空")
    alias = _CRON_ALIASES.get(expr.lower())
    if alias:
        return alias
    parts = expr.split()
    if len(parts) == 6:
        parts = parts[1:]  # 丢掉秒（调度器最小粒度是分钟）
    elif len(parts) == 7:
        parts = parts[1:6]  # 秒 + 分 时 日 月 周 + 年
    if len(parts) != 5:
        raise ValueError("cron 表达式需要 5 段或 6 段（若依格式：秒 分 时 日 月 周）")
    return " ".join(p.replace("?", "*") for p in parts)


def validate_cron(expression: str) -> bool:
    try:
        _match_cron(expression, datetime.now())
        return True
    except Exception:
        return False


def _parse_field(field: str, lo: int, hi: int) -> Set[int]:
    values: Set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = max(1, int(step_text))
        if part in ("*", "?"):
            start, end = lo, hi
        elif "-" in part:
            left, right = part.split("-", 1)
            start, end = int(left), int(right)
        else:
            start = end = int(part)
        if start < lo or end > hi or start > end:
            raise ValueError(f"cron 字段越界: {field}")
        values.update(range(start, end + 1, step))
    if not values:
        raise ValueError(f"cron 字段为空: {field}")
    return values


def _weekday_set(field: str) -> Set[int]:
    """Quartz 星期 → Python weekday（0=周一）。"""
    raw = _parse_field(field, 0, 7)
    out: Set[int] = set()
    for value in raw:
        if value == 0:
            out.add(6)  # 0 也当周日
        else:
            out.add((value + 5) % 7)  # 1(周日)→6, 2(周一)→0, ..., 7(周六)→5
    return out


def _match_cron(expression: str, dt: datetime) -> bool:
    parts = _normalize_cron(expression).split()
    minute, hour, dom, month, dow = parts
    minutes = _parse_field(minute, 0, 59)
    hours = _parse_field(hour, 0, 23)
    doms = _parse_field(dom, 1, 31)
    months = _parse_field(month, 1, 12)
    dows = _weekday_set(dow)

    if dt.minute not in minutes or dt.hour not in hours or dt.month not in months:
        return False

    dom_restricted = dom not in ("*", "?")
    dow_restricted = dow not in ("*", "?")
    dom_ok = dt.day in doms
    dow_ok = dt.weekday() in dows
    if dom_restricted and dow_restricted:
        # 标准 cron：两者都限定时按「或」匹配（与 Quartz 的 ? 语义兼容）
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def next_run_time(expression: str, after: Optional[datetime] = None) -> str:
    """从 after 起向后扫描，返回下一次执行时间（找不到 400 天内返回空串）。"""
    cursor = (after or datetime.now()).replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = cursor + timedelta(days=400)
    while cursor < limit:
        try:
            if _match_cron(expression, cursor):
                return cursor.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return ""
        cursor += timedelta(minutes=1)
    return ""


# ---------------------------------------------------------------------------
# 任务实现（每个任务自己开数据库会话，调度线程不持有请求会话）
# ---------------------------------------------------------------------------

async def _task_practice_session_cleanup() -> str:
    from app.models.question import UserPracticeSession

    async with async_session_factory() as db:
        result = await db.execute(
            update(UserPracticeSession)
            .where(
                UserPracticeSession.status == "ongoing",
                UserPracticeSession.create_time < datetime.now() - timedelta(hours=2),
            )
            .values(status="expired", update_time=datetime.now())
        )
        await db.commit()
        return f"清理过期练习会话 {int(result.rowcount or 0)} 条"


async def _task_document_pipeline_recovery() -> str:
    from app.services.rag.document_pipeline import recover_stale_documents

    result = await recover_stale_documents()
    return f"回收中断文档 {int((result or {}).get('recovered', 0))} 篇"


async def _task_dict_cache_refresh() -> str:
    from app.api.v1 import system as system_api

    async with async_session_factory() as db:
        system_api._DICT_LOADED = False  # noqa: SLF001 - 调度任务与字典模块共用缓存
        await system_api._ensure_dict_loaded(db)  # noqa: SLF001
        await db.commit()
        return f"字典缓存已刷新，共 {len(system_api._DICT_TYPES)} 个类型"  # noqa: SLF001


async def _task_log_cleanup() -> str:
    from app.models.monitor import SysLogininfor, SysOperLog

    now = datetime.now()
    async with async_session_factory() as db:
        oper = await db.execute(
            delete(SysOperLog).where(SysOperLog.oper_time < now - timedelta(days=90))
        )
        login = await db.execute(
            delete(SysLogininfor).where(SysLogininfor.login_time < now - timedelta(days=90))
        )
        job_log = await db.execute(
            delete(SysJobLog).where(SysJobLog.create_time < now - timedelta(days=30))
        )
        await db.commit()
        return (
            f"清理操作日志 {int(oper.rowcount or 0)} 条、"
            f"登录日志 {int(login.rowcount or 0)} 条、调度日志 {int(job_log.rowcount or 0)} 条"
        )


_TASKS: Dict[str, Callable[[], "asyncio.Future[str] | object"]] = {
    "practiceSessionCleanup": _task_practice_session_cleanup,
    "documentPipelineRecovery": _task_document_pipeline_recovery,
    "dictCacheRefresh": _task_dict_cache_refresh,
    "logCleanup": _task_log_cleanup,
}


def available_targets() -> list[str]:
    return sorted(_TASKS)


async def run_job(job_id: int, *, manual: bool = False) -> dict:
    """执行一次任务并写调度日志。并发策略为「禁止」时，上一次未结束则跳过。"""
    global _running_job_ids

    async with async_session_factory() as db:
        job = await db.get(SysJob, int(job_id))
        if job is None:
            return {"ok": False, "message": "任务不存在"}
        if int(job_id) in _running_job_ids:
            db.add(
                SysJobLog(
                    job_name=job.job_name,
                    job_group=job.job_group,
                    invoke_target=job.invoke_target,
                    job_message="上一次执行尚未结束，本次跳过",
                    status=1,
                    exception_info="concurrent=1（禁止并发）",
                    create_time=datetime.now(),
                )
            )
            await db.commit()
            return {"ok": False, "message": "任务正在执行中，已跳过"}

        _running_job_ids.add(int(job_id))
        started = datetime.now()
        try:
            task = _TASKS.get(job.invoke_target)
            if task is None:
                raise ValueError(
                    f"不支持的调用目标：{job.invoke_target}；可用：{', '.join(available_targets())}"
                )
            message = str(await task())
            status = 0
            exception_info = None
        except Exception as exc:  # noqa: BLE001 - 任务失败要落日志而不是让调度器崩
            logger.exception("[job] 执行失败 id={} target={}", job_id, job.invoke_target)
            message = f"执行失败：{exc}"
            status = 1
            exception_info = f"{type(exc).__name__}: {exc}"
        finally:
            _running_job_ids.discard(int(job_id))

        log = SysJobLog(
            job_name=job.job_name,
            job_group=job.job_group,
            invoke_target=job.invoke_target,
            job_message=message[:500],
            status=status,
            exception_info=exception_info,
            create_time=started,
        )
        db.add(log)
        job.update_time = datetime.now()
        await db.commit()
        await db.refresh(log)
        return {
            "ok": status == 0,
            "jobId": int(job.job_id),
            "jobLogId": int(log.job_log_id),
            "message": message,
            "manual": manual,
        }


_running_job_ids: Set[int] = set()
_last_fired_minute: Dict[int, str] = {}


async def _loop() -> None:
    # 等应用启动完成（Redis/DB/静态资源挂载）再开始扫表
    await asyncio.sleep(10)
    while True:
        try:
            async with async_session_factory() as db:
                jobs = list(
                    (
                        await db.execute(
                            select(SysJob).where(SysJob.status == "0").order_by(SysJob.job_id)
                        )
                    )
                    .scalars()
                    .all()
                )
            now = datetime.now()
            minute_key = now.strftime("%Y%m%d%H%M")
            for job in jobs:
                if _last_fired_minute.get(int(job.job_id)) == minute_key:
                    continue
                try:
                    if _match_cron(job.cron_expression, now):
                        _last_fired_minute[int(job.job_id)] = minute_key
                        asyncio.create_task(run_job(int(job.job_id)))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[job] cron 解析失败 id={} expr={}: {}", job.job_id, job.cron_expression, exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("[job] 调度循环异常: {}", exc)
        await asyncio.sleep(20)
