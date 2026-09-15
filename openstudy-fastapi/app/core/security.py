"""
安全认证模块
JWT Token 生成/验证 + Redis 存储
"""

from datetime import datetime, timedelta
from typing import Optional
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
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


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
