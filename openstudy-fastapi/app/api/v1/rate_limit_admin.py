"""
AI 限流管理 API（后台「限流监控」页使用）

提供四块能力：
  1. 限流配置的查看/修改（Redis 实时生效，见 app/core/rate_limit_config.py）
  2. 违规记录分页查询（sys_ai_rate_limit_log）
  3. 计数器查看/清除（scan rl:ai:* —— 清除 = 解除限流）
  4. 封禁/解封（sys_user.status + 踢会话）

⚠️ 全部接口仅管理员可用（roles 含 admin 系列，或 perms 含 *:*:*，
   口径与 ai_config.py 的 _is_admin 一致）。
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import time

from app.database import get_db, async_session_factory
from app.core.security import get_current_user
from app.core.response import success, error, paginate
from app.redis import redis_client
from app.core import rate_limit_config

router = APIRouter(prefix="/monitor/ratelimit")


# ---------- 权限 ----------


def _is_admin(current_user: dict) -> bool:
    """是否管理员：roles 含 admin 系列，或权限含通配 `*:*:*`（口径同 ai_config.py）"""
    roles = current_user.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    if any(str(r).lower() in ("admin", "administrator", "superadmin", "super_admin") for r in roles):
        return True
    perms = current_user.get("perms") or []
    if isinstance(perms, str):
        perms = [perms]
    return "*:*:*" in perms


def _uid(current_user: dict) -> Optional[int]:
    uid = current_user.get("user_id")
    try:
        return int(uid) if uid else None
    except (TypeError, ValueError):
        return None


async def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return current_user


# ---------- 1. 配置 ----------


@router.get("/config")
async def get_rate_limit_config(current_user: dict = Depends(_require_admin)):
    """当前生效的限流配置（并标注每项来自 redis 还是 env 默认值）"""
    cfg = await rate_limit_config.get_config()
    return success(cfg)


class RateLimitConfigBody(BaseModel):
    enabled: Optional[bool] = None
    userPerMinute: Optional[int] = Field(None, ge=1, le=100000)
    dailyLimit: Optional[int] = Field(None, ge=1, le=1000000)
    ipPerMinute: Optional[int] = Field(None, ge=1, le=1000000)

    class Config:
        extra = "forbid"


@router.put("/config")
async def update_rate_limit_config(
    body: RateLimitConfigBody,
    current_user: dict = Depends(_require_admin),
):
    """修改限流配置（整体覆盖写入 Redis，立即生效，无需重启）"""
    current = await rate_limit_config.get_config()
    new = await rate_limit_config.save_config(
        enabled=body.enabled if body.enabled is not None else current["enabled"],
        user_per_minute=body.userPerMinute if body.userPerMinute is not None else current["userPerMinute"],
        daily_limit=body.dailyLimit if body.dailyLimit is not None else current["dailyLimit"],
        ip_per_minute=body.ipPerMinute if body.ipPerMinute is not None else current["ipPerMinute"],
    )
    return success(new)


# ---------- 2. 违规记录 ----------


def _format_log(row) -> dict:
    return {
        "id": row.id,
        "userId": row.user_id,
        "userName": row.user_name,
        "ip": row.ip,
        "path": row.path,
        "limitType": row.limit_type,
        "currentCount": row.current_count,
        "limitValue": row.limit_value,
        "createTime": row.create_time.isoformat() if row.create_time else None,
    }


@router.get("/violations")
async def list_violations(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    userId: Optional[int] = Query(None),
    ip: Optional[str] = Query(None),
    limitType: Optional[str] = Query(None),
    beginTime: Optional[str] = Query(None),
    endTime: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(_require_admin),
):
    """分页查询限流违规记录（过滤：用户 / IP / 类型 / 时间段）"""
    from app.models.ai_rate_limit_log import SysAiRateLimitLog

    query = select(SysAiRateLimitLog)
    if userId is not None:
        query = query.where(SysAiRateLimitLog.user_id == userId)
    if ip:
        query = query.where(SysAiRateLimitLog.ip == ip)
    if limitType:
        query = query.where(SysAiRateLimitLog.limit_type == limitType)
    for field, value, op in (
        (SysAiRateLimitLog.create_time, beginTime, "ge"),
        (SysAiRateLimitLog.create_time, endTime, "le"),
    ):
        if not value:
            continue
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return error(f"时间格式不合法: {value}")
        query = query.where(field >= dt) if op == "ge" else query.where(field <= dt)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = list(
        (
            await db.execute(
                query.order_by(SysAiRateLimitLog.create_time.desc(), SysAiRateLimitLog.id.desc())
                .offset((pageNum - 1) * pageSize)
                .limit(pageSize)
            )
        )
        .scalars()
        .all()
    )
    return paginate(total, [_format_log(r) for r in rows])


# ---------- 3. 计数器 ----------


def _parse_counter_key(key: str):
    """解析 rl:ai:{kind}:{id}:{bucket} → (kind, id, bucket)；不匹配返回 None"""
    parts = key.split(":")
    # 形如 rl:ai:{ip|umin|uday}:{标识}:{桶}，共 5 段（IP 按 v4 处理，不含冒号）
    if len(parts) != 5 or parts[0] != "rl" or parts[1] != "ai":
        return None
    kind, ident, bucket = parts[2], parts[3], parts[4]
    if kind not in ("ip", "umin", "uday"):
        return None
    return kind, ident, bucket


async def _scan_rl_keys(pattern: str = "rl:ai:*") -> List[str]:
    pool = redis_client.client
    keys = []
    async for k in pool.scan_iter(match=pattern, count=200):
        keys.append(k)
    return keys


@router.get("/counters")
async def list_counters(
    ip: Optional[str] = Query(None),
    current_user: dict = Depends(_require_admin),
):
    """扫描当前限流计数器（rl:ai:*），让管理员看到谁在逼近限额

    ?ip=1.2.3.4 只看某个 IP；用户维度可用 type=userMin/userDay 筛。
    """
    pattern = f"rl:ai:ip:{ip}:*" if ip else "rl:ai:*"
    pool = redis_client.client
    try:
        keys = await _scan_rl_keys(pattern)
    except Exception as e:
        return error(f"Redis 扫描失败: {e}")

    now = int(time.time())
    minute_bucket = now // 60
    day = time.strftime("%Y%m%d")

    counters = []
    if keys:
        values = await pool.mget(keys)
        for key, val in zip(keys, values):
            if val is None:
                continue
            kind, ident, bucket = _parse_counter_key(key)
            if kind is None:
                continue
            if kind == "ip":
                typ, target = "ipMin", ident
            elif kind == "umin":
                typ, target = "userMin", ident
            elif kind == "uday":
                typ, target = "userDay", ident
            else:
                continue
            # 粗略剩余时间：分钟桶到本分钟结束，日桶到当天结束
            if kind == "uday":
                ttl = max(0, 86400 - (now % 86400))
            else:
                ttl = max(0, (minute_bucket + 1) * 60 - now)
            counters.append(
                {
                    "key": key,
                    "type": typ,
                    "target": target,
                    "bucket": bucket,
                    "count": int(val),
                    "expiresIn": ttl,
                    "current": (bucket == day) if kind == "uday" else (bucket == str(minute_bucket)),
                }
            )
    # 补查用户名：对 userMin/userDay 类型的计数器，把 target(user_id) 映射成用户名
    user_ids = set()
    for c in counters:
        if c["type"] in ("userMin", "userDay"):
            try:
                user_ids.add(int(c["target"]))
            except (ValueError, TypeError):
                pass
    user_names = {}
    if user_ids:
        try:
            from sqlalchemy import text
            async with async_session_factory() as db:
                uid_list = ",".join(str(u) for u in user_ids)
                result = await db.execute(
                    text(f"SELECT user_id, user_name FROM sys_user WHERE user_id IN ({uid_list})")
                )
                for row in result:
                    user_names[str(row[0])] = row[1]
        except Exception:
            pass
    for c in counters:
        if c["type"] in ("userMin", "userDay"):
            c["userName"] = user_names.get(c["target"], "")

    counters.sort(key=lambda c: (-c["count"], c["key"]))
    return success({"total": len(counters), "counters": counters})


class ClearCountersBody(BaseModel):
    keys: Optional[List[str]] = None
    ip: Optional[str] = None
    userId: Optional[int] = None

    class Config:
        extra = "forbid"


@router.delete("/counters")
async def clear_counters(
    body: ClearCountersBody,
    current_user: dict = Depends(_require_admin),
):
    """清除限流计数器（= 解除限流）

    按 keys 精确清，或按 ip / userId 清整个维度。三项都空 = 清全部。
    """
    pool = redis_client.client
    to_delete: List[str] = []
    if body.keys:
        to_delete.extend(k for k in body.keys if _parse_counter_key(k))
    if body.ip:
        to_delete.extend(await _scan_rl_keys(f"rl:ai:ip:{body.ip}:*"))
    if body.userId is not None:
        to_delete.extend(await _scan_rl_keys(f"rl:ai:umin:{body.userId}:*"))
        to_delete.extend(await _scan_rl_keys(f"rl:ai:uday:{body.userId}:*"))
    if not body.keys and body.ip is None and body.userId is None:
        # ⚠️ 不能用 rl:ai:* —— 会误删 rl:ai:config（限流配置 hash）
        to_delete.extend(await _scan_rl_keys("rl:ai:ip:*"))
        to_delete.extend(await _scan_rl_keys("rl:ai:umin:*"))
        to_delete.extend(await _scan_rl_keys("rl:ai:uday:*"))

    to_delete = list(dict.fromkeys(to_delete))
    deleted = 0
    if to_delete:
        deleted = await pool.delete(*to_delete)
    return success({"deleted": deleted, "keys": to_delete})




# ---------- 3.5 已封禁用户列表 ----------


@router.get("/banned")
async def list_banned_users(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(_require_admin),
):
    """列出当前被封禁的用户（sys_user.status = '1'）"""
    from sqlalchemy import text

    result = await db.execute(
        text("SELECT user_id, user_name, nick_name, status, update_time FROM sys_user WHERE status = '1' ORDER BY user_id")
    )
    rows = result.all()
    return success([
        {
            "userId": r[0],
            "userName": r[1],
            "nickName": r[2],
            "status": r[3],
            "updateTime": r[4].isoformat() if r[4] else None,
        }
        for r in rows
    ])


# ---------- 4. 封禁 / 解封 ----------

USER_TOKEN_PREFIX = "openstudy-py:user_token:"
LOGIN_TOKEN_PREFIX = "openstudy-py:login_tokens:"


async def _kick_user_sessions(user_id: int) -> int:
    """踢掉该用户所有会话：读 user_token:{uid} 拿 token，删 token key，再删映射本身。

    与 security.remove_token（单 token 退出）不同，这里是管理员封禁场景，
    要把「该用户当前持有的一切 token」都清干净。
    """
    pool = redis_client.client
    removed = 0
    user_token_key = f"{USER_TOKEN_PREFIX}{user_id}"
    token = await pool.get(user_token_key)
    if token:
        removed += await pool.delete(f"{LOGIN_TOKEN_PREFIX}{token}")
    removed += await pool.delete(user_token_key)
    return removed


async def _user_role_keys(db: AsyncSession, user_id: int) -> List[str]:
    """该用户的角色 key 列表（判断「不能封管理员」用）"""
    from app.models.user import SysUser

    user = await db.get(SysUser, user_id)
    if not user:
        return []
    return [r.role_key for r in (user.roles or [])]


class BanBody(BaseModel):
    userId: int
    reason: Optional[str] = None

    class Config:
        extra = "forbid"


class UnbanBody(BaseModel):
    userId: int

    class Config:
        extra = "forbid"


@router.post("/ban")
async def ban_user(
    body: BanBody,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(_require_admin),
):
    """封禁用户：sys_user.status 置 '1' 并踢掉其全部会话（立即下线）

    不允许封自己，也不允许封管理员（防止误操作把整个系统锁死）。
    """
    from app.models.user import SysUser

    me = _uid(current_user)
    if body.userId == me:
        return error("不能封禁自己")

    user = await db.get(SysUser, body.userId)
    if not user:
        return error("用户不存在")

    role_keys = [str(r.role_key).lower() for r in (user.roles or [])]
    if "admin" in role_keys:
        return error("不能封禁管理员账号")

    user.status = "1"
    user.update_by = current_user.get("user_name", "admin")
    user.update_time = datetime.now()
    await db.commit()

    kicked = await _kick_user_sessions(body.userId)
    return success({"userId": body.userId, "status": "1", "kickedSessions": kicked})


@router.post("/unban")
async def unban_user(
    body: UnbanBody,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(_require_admin),
):
    """解封用户：status 恢复 '0'（被踢的会话不会回来，需重新登录）"""
    from app.models.user import SysUser

    user = await db.get(SysUser, body.userId)
    if not user:
        return error("用户不存在")

    user.status = "0"
    user.update_by = current_user.get("user_name", "admin")
    user.update_time = datetime.now()
    await db.commit()
    return success({"userId": body.userId, "status": "0"})
