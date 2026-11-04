"""后台监控 API（服务监控 / Redis 缓存 / 在线会话）。

这些接口此前在 FastAPI 侧完全缺失，但后台菜单和页面都在，
所有请求落到 catch_all 后表现成“永远空数据”。这里补最小可用实现：
- `/monitor/server`：真实 CPU / 内存 / 磁盘 / Python 运行时；
- `/monitor/cache*`：真实 Redis INFO / key 浏览 / 清理；
- `/monitor/online*`：从 Redis 登录 token 列真实在线会话，并支持强退。

所有路径统一挂 `require_admin`，避免普通用户看服务器信息或清缓存。
"""

from __future__ import annotations

import json
import os
import platform
import socket
import sys
import time
from typing import Any, Dict, List

import psutil
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import success, error, paginate
from app.core.security import require_admin
from app.database import get_db
from app.redis import redis_client

router = APIRouter(prefix="/monitor")


def _bytes_to_gb(value: float) -> float:
    return round(float(value) / (1024 ** 3), 2)


@router.get("/server")
async def server_info(current_user: dict = Depends(require_admin)):
    """服务监控：真实数据（不再依赖 Java/JVM 的那套字段，但保持前端兼容键名）。"""
    vm = psutil.virtual_memory()
    cpu_percent = psutil.cpu_percent(interval=0.05)
    process = psutil.Process(os.getpid())
    sys_files: List[Dict[str, Any]] = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except Exception:
            continue
        sys_files.append(
            {
                "dirName": part.mountpoint,
                "sysTypeName": part.fstype or "本地磁盘",
                "typeName": "固定盘",
                "total": f"{_bytes_to_gb(usage.total)} GB",
                "free": f"{_bytes_to_gb(usage.free)} GB",
                "used": f"{_bytes_to_gb(usage.used)} GB",
                "usage": round(usage.percent, 1),
            }
        )
    runtime_seconds = max(0, time.time() - process.create_time())
    days, rem = divmod(int(runtime_seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    return success(
        {
            "cpu": {
                "cpuNum": psutil.cpu_count(logical=True) or 1,
                "used": round(cpu_percent, 1),
                # 用户态/系统态无法从 psutil 直接拆分，给同一总量避免页面空白
                "sys": round(cpu_percent, 1),
                "free": round(max(0.0, 100.0 - cpu_percent), 1),
            },
            "mem": {
                "total": _bytes_to_gb(vm.total),
                "used": _bytes_to_gb(vm.used),
                "free": _bytes_to_gb(vm.available),
                "usage": round(vm.percent, 1),
            },
            "jvm": {
                "name": platform.python_implementation(),
                "version": platform.python_version(),
                "startTime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(process.create_time())),
                "runTime": f"{days}天{hours}小时{minutes}分钟",
                "home": sys.executable,
                "inputArgs": " ".join(sys.argv),
                "total": round(process.memory_info().rss / 1024 / 1024, 1),
                "used": round(process.memory_info().rss / 1024 / 1024, 1),
                "free": 0,
                "usage": round(vm.percent, 1),
            },
            "sys": {
                "computerName": socket.gethostname(),
                "osName": platform.platform(),
                "computerIp": socket.gethostbyname(socket.gethostname()),
                "osArch": platform.machine(),
                "userDir": os.getcwd(),
            },
            "sysFiles": sys_files,
        }
    )


@router.get("/cache")
async def cache_info(current_user: dict = Depends(require_admin)):
    try:
        info = await redis_client.client.info()
        db_size = await redis_client.client.dbsize()
        try:
            commandstats = await redis_client.client.info("commandstats")
        except Exception:
            commandstats = {}
        commands = []
        for key, value in (commandstats or {}).items():
            if not key.startswith("cmdstat_"):
                continue
            name = key[len("cmdstat_"):]
            calls = 0
            for part in str(value).split(","):
                if part.startswith("calls="):
                    try:
                        calls = int(part.split("=", 1)[1])
                    except ValueError:
                        calls = 0
            commands.append({"name": name, "value": calls})
        return success(
            {
                "info": info,
                "dbSize": db_size,
                "commandStats": commands,
            }
        )
    except Exception as e:
        return error(f"读取 Redis 信息失败：{e}")


@router.get("/cache/getNames")
async def cache_names(current_user: dict = Depends(require_admin)):
    names: Dict[str, int] = {}
    try:
        async for key in redis_client.client.scan_iter(match="openstudy-py:*"):
            parts = str(key).split(":", 2)
            if len(parts) >= 3:
                names[parts[1]] = names.get(parts[1], 0) + 1
    except Exception as e:
        return error(f"读取缓存列表失败：{e}")
    return success([
        {"cacheName": name, "remark": f"{count} 个键"}
        for name, count in sorted(names.items())
    ])


@router.get("/cache/getKeys/{cache_name}")
async def cache_keys(cache_name: str, current_user: dict = Depends(require_admin)):
    try:
        pattern = f"openstudy-py:{cache_name}:*"
        keys = [str(k) async for k in redis_client.client.scan_iter(match=pattern)]
        return success(keys)
    except Exception as e:
        return error(f"读取缓存键失败：{e}")


@router.get("/cache/getValue/{cache_name}/{cache_key:path}")
async def cache_value(cache_name: str, cache_key: str, current_user: dict = Depends(require_admin)):
    try:
        raw = await redis_client.client.get(cache_key)
        if raw is None and not cache_key.startswith("openstudy-py:"):
            raw = await redis_client.client.get(f"openstudy-py:{cache_name}:{cache_key}")
        value = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else (raw or "")
        return success({"cacheName": cache_name, "cacheKey": cache_key, "cacheValue": value})
    except Exception as e:
        return error(f"读取缓存值失败：{e}")


@router.delete("/cache/clearCacheName/{cache_name}")
async def clear_cache_name(cache_name: str, current_user: dict = Depends(require_admin)):
    try:
        pattern = f"openstudy-py:{cache_name}:*"
        keys = [str(k) async for k in redis_client.client.scan_iter(match=pattern)]
        if keys:
            await redis_client.client.delete(*keys)
        return success({"deleted": len(keys)})
    except Exception as e:
        return error(f"清理缓存失败：{e}")


@router.delete("/cache/clearCacheKey/{cache_key:path}")
async def clear_cache_key(cache_key: str, current_user: dict = Depends(require_admin)):
    try:
        deleted = await redis_client.client.delete(cache_key)
        return success({"deleted": int(deleted or 0)})
    except Exception as e:
        return error(f"清理缓存失败：{e}")


@router.delete("/cache/clearCacheAll")
async def clear_cache_all(current_user: dict = Depends(require_admin)):
    try:
        # 绝对不能把登录 token 一起清掉：那会把全站用户瞬间踢下线。
        keys = [
            str(k) async for k in redis_client.client.scan_iter(match="openstudy-py:*")
            if not str(k).startswith(("openstudy-py:login_tokens:", "openstudy-py:user_token:"))
        ]
        if keys:
            await redis_client.client.delete(*keys)
        return success({"deleted": len(keys)})
    except Exception as e:
        return error(f"清理缓存失败：{e}")


@router.get("/online/list")
async def online_list(
    ipaddr: str = Query(""),
    userName: str = Query(""),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    current_user: dict = Depends(require_admin),
):
    rows: List[Dict[str, Any]] = []
    try:
        async for key in redis_client.client.scan_iter(match="openstudy-py:login_tokens:*"):
            raw = await redis_client.client.get(key)
            if not raw:
                continue
            try:
                data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            except Exception:
                continue
            token = str(key).rsplit(":", 1)[-1]
            row = {
                "tokenId": token,
                "userName": data.get("user_name") or "",
                "ipaddr": data.get("login_ip") or "127.0.0.1",
                "loginLocation": "本机",
                "os": platform.system(),
                "browser": "浏览器",
                "loginTime": data.get("login_time") or "",
                "userId": data.get("user_id"),
            }
            if ipaddr and ipaddr not in row["ipaddr"]:
                continue
            if userName and userName not in row["userName"]:
                continue
            rows.append(row)
    except Exception as e:
        return error(f"读取在线用户失败：{e}")
    rows.sort(key=lambda r: str(r.get("loginTime") or ""), reverse=True)
    total = len(rows)
    start = (pageNum - 1) * pageSize
    return paginate(total, rows[start:start + pageSize])


@router.delete("/online/{token_id}")
async def force_logout(token_id: str, current_user: dict = Depends(require_admin)):
    try:
        key = f"openstudy-py:login_tokens:{token_id}"
        raw = await redis_client.client.get(key)
        if not raw:
            return error("会话不存在或已下线", code=404)
        data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        await redis_client.client.delete(key)
        await redis_client.client.delete(f"openstudy-py:user_token:{data.get('user_id')}")
        return success()
    except Exception as e:
        return error(f"强退失败：{e}")
