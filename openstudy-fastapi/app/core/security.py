"""
安全认证模块
JWT Token 生成/验证 + Redis 存储
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings
from app.redis import redis_client
import json
import uuid

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer Token 提取
security = HTTPBearer(auto_error=False)

# Redis Key 前缀（加 openstudy-py: 前缀，与 Spring Boot 项目隔离，避免序列化冲突）
LOGIN_TOKEN_PREFIX = "openstudy-py:login_tokens:"
USER_TOKEN_PREFIX = "openstudy-py:user_token:"


def hash_password(password: str) -> str:
    """密码加密"""
    # bcrypt 限制密码不超过 72 字节
    password_bytes = password.encode("utf-8")[:72]
    return pwd_context.hash(password_bytes.decode("utf-8", errors="ignore"))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码

    ⚠️ 必须与 hash_password 用同样的 72 字节截断：bcrypt 只认前 72 字节，
    新版 bcrypt(>=4.1/5.x) 对超长输入会直接抛 ValueError 而不是静默截断。
    """
    plain_bytes = plain_password.encode("utf-8")[:72]
    return pwd_context.verify(plain_bytes.decode("utf-8", errors="ignore"), hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT Token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """验证 JWT Token"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


async def create_login_token(
    user_id: int,
    user_name: str,
    nick_name: str,
    roles: list,
    perms: list,
) -> str:
    """创建登录 Token 并存储到 Redis"""
    token = str(uuid.uuid4())

    # Token 数据
    token_data = {
        "user_id": user_id,
        "user_name": user_name,
        "nick_name": nick_name,
        "roles": roles,
        "perms": perms,
        "login_time": datetime.utcnow().isoformat(),
    }

    # 存储到 Redis
    await redis_client.client.setex(
        f"{LOGIN_TOKEN_PREFIX}{token}",
        settings.JWT_EXPIRE_MINUTES * 60,
        json.dumps(token_data, ensure_ascii=False),
    )

    # 记录用户当前 Token（单点登录）
    await redis_client.client.setex(
        f"{USER_TOKEN_PREFIX}{user_id}",
        settings.JWT_EXPIRE_MINUTES * 60,
        token,
    )

    return token


async def get_login_user(token: str) -> Optional[dict]:
    """从 Redis 获取登录用户信息"""
    data = await redis_client.client.get(f"{LOGIN_TOKEN_PREFIX}{token}")
    if data:
        return json.loads(data)
    return None


async def refresh_token(token: str) -> None:
    """刷新 Token 过期时间"""
    key = f"{LOGIN_TOKEN_PREFIX}{token}"
    await redis_client.client.expire(key, settings.JWT_EXPIRE_MINUTES * 60)


async def remove_token(token: str) -> None:
    """删除 Token（退出登录）"""
    data = await redis_client.client.get(f"{LOGIN_TOKEN_PREFIX}{token}")
    if data:
        user_data = json.loads(data)
        await redis_client.client.delete(f"{LOGIN_TOKEN_PREFIX}{token}")
        await redis_client.client.delete(f"{USER_TOKEN_PREFIX}{user_data['user_id']}")


def is_admin_user(current_user: Optional[dict]) -> bool:
    """当前用户是否管理员（`roles` 里含 `admin`）

    口径与 `api/v1/notes.py` / `api/v1/questions.py` 一致（**最严的那版**）——
    这两处守的也是「个人数据」，且有测试覆盖。
    ⚠️ `api/v1/ai_config.py` 另有一份更宽的实现（额外认 `perms` 含 `*:*:*`、
    以及 administrator / superadmin 等变体）。**这里刻意没有跟着放宽** ——
    放宽权限判定是安全敏感改动，该单独评估，不该顺手做。
    """
    roles = (current_user or {}).get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    return "admin" in roles


def resolve_user_scope(
    current_user: Optional[dict], requested_user_id
) -> Tuple[Optional[int], Optional[str]]:
    """把「请求里带的 userId」收敛成**实际允许操作**的 user_id

    Returns:
        `(user_id, None)` 通过；`(None, err_msg)` 越权 / 非法

    **为什么需要它**：这类接口原来写的是

        user_id = userId or current_user.get("user_id") or 0

    于是**任何登录用户只要在请求里传别人的 userId，就能以他人身份读写**
    （水平越权 / IDOR）。本函数把「不同 id」这条路收掉：

      · 不传 / 传空（`None` / `""` / `0` / `"0"`）→ 用当前登录用户。
        **有意保留原来的 `or` 语义** —— 改的是「传了不同 id」这条路径，
        不是「空值」；有些调用方（含前端自检面板）传 0 表示「没指定」。
      · 传自己 → 通过。
      · 传别人 → 只有管理员放行，否则拒绝。

    ⚠️ **错误形状由调用方决定，不能一刀切**：
      · 非流式会话接口 → `error(msg, code=403)`（本仓库 `error()` 的形状）
      · SSE 流（`/assistant/stream`、`/agent/stream`）→ 前端判的是 `response.ok`，
        所以要 `JSONResponse(403, error(...))`
      · `/ai/agent/execute` → **必须**回 `fail(...)` 信封。前端 ds-free 循环判的是
        `result.success !== false`，而 `error()` 没有 `success` 字段 →
        会被 `undefined !== false` 判成**成功**，显示一张绿色成功卡片。
    """
    current_id = int((current_user or {}).get("user_id") or 0)

    rid = 0
    if requested_user_id not in (None, ""):
        try:
            rid = int(requested_user_id)
        except (TypeError, ValueError):
            return None, f"userId 不是合法整数：{requested_user_id!r}"

    if rid == 0 or rid == current_id:
        return current_id, None
    if is_admin_user(current_user):
        return rid, None
    return None, "无权以他人身份操作"


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """获取当前登录用户（必须登录；游客仅允许 GET/HEAD/OPTIONS）"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
        )

    token = credentials.credentials
    user_data = await get_login_user(token)

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期",
        )

    # 游客只读：写操作统一在入口拦截，避免绕过前端提示直接写库（退出登录除外）
    is_guest = "visitor" in user_data.get("roles", [])
    is_logout = request.url.path.endswith("/logout")
    if is_guest and not is_logout and request.method not in ("GET", "HEAD", "OPTIONS"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="游客仅可浏览，登录后才能进行该操作",
        )

    # 刷新 Token 过期时间
    await refresh_token(token)

    return user_data


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """获取可选的登录用户（不强制要求登录）"""
    if not credentials:
        return None

    token = credentials.credentials
    return await get_login_user(token)


async def require_roles(*required_roles: str):
    """要求特定角色"""
    async def role_checker(current_user: dict = Depends(get_current_user)):
        user_roles = current_user.get("roles", [])
        if not any(role in user_roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )
        return current_user
    return role_checker


async def require_perms(*required_perms: str):
    """要求特定权限"""
    async def perm_checker(current_user: dict = Depends(get_current_user)):
        user_perms = current_user.get("perms", [])
        if "*:*:*" not in user_perms:
            if not any(perm in user_perms for perm in required_perms):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="权限不足",
                )
        return current_user
    return perm_checker


# ============================================================
# 后台管理接口的统一守卫（2026-10-22）
# ============================================================
#
# 为什么要单独加一个：
#   后台 `/system/**` 下有 20 多个接口原本**只校验了「登录」，没校验「是不是管理员」**。
#   实测：演示用户 user1 直接 GET /system/user/list 能拿到全部用户列表，
#   PUT /system/config 能改系统参数 —— 这是实打实的水平越权。
#
# 为什么不复用上面的 require_roles：
#   那个抛的是 HTTPException(403)，而本项目前端统一按 `body.code` 判断
#   （HTTP 200 + code=403）。抛 HTTPException 会让前端走到 axios 的 catch 分支，
#   提示文案不可控。这里按项目既有风格返回 200 + code=403。
#
# 用法：
#   @router.get("/system/config/list")
#   async def list_configs(..., current_user: dict = Depends(require_admin)):
#       ...
async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """要求管理员身份；非管理员抛 403（全局处理器会转成 `200 + code=403`）。

    说明：本项目 `core/exceptions.py: http_exception_handler` 已把
    `HTTPException(403)` 统一转成 `{"code": 403, "msg": ...}` 且 HTTP 状态为 200，
    与前端 `code !== 200` 的判断完全兼容。所以这里直接抛即可，
    不要在依赖里 return error(...) —— 那样 FastAPI 会把它当成正常返回值序列化，
    调用方拿到的是「成功响应里塞了个 error 对象」，反而更危险。

    ⚠️ 这是后台管理接口的**唯一入口守卫**，新增 `/system/**`、`/monitor/**`
    接口时必须挂上，否则普通登录用户可直接调用。
    """
    if not is_admin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，仅管理员可访问",
        )
    return current_user

