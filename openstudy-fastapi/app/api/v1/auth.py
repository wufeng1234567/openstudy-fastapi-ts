"""
认证相关 API
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.core.security import (
    create_login_token,
    hash_password,
    verify_password,
    get_current_user,
    remove_token,
)
from app.core.response import success, error
from app.repositories.user_repo import UserRepository
from app.utils.redis_util import get_cache, set_cache, delete_cache
from app.models.config import SysConfig
import uuid
import random
import string

router = APIRouter()


@router.get("/captchaImage")
async def captcha_image(db: AsyncSession = Depends(get_db)):
    """生成验证码图片"""
    import base64
    import io
    from PIL import Image, ImageDraw, ImageFont

    # 查询验证码开关配置
    config_query = select(SysConfig).where(SysConfig.config_key == "sys.account.captchaEnabled")
    config_result = await db.execute(config_query)
    captcha_config = config_result.scalar_one_or_none()
    captcha_enabled = captcha_config.config_value.lower() == "true" if captcha_config else True

    captcha_id = str(uuid.uuid4())

    if not captcha_enabled:
        return success({
            "uuid": captcha_id,
            "img": "",
            "captchaEnabled": False,
        })

    # 生成4位随机字符验证码
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=4))

    # 存储到 Redis，5分钟过期
    await set_cache(f"captcha:{captcha_id}", code.lower(), expire=300)

    # 创建验证码图片
    width, height = 160, 60
    image = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)

    # 绘制干扰线
    for _ in range(5):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)))

    # 绘制噪点
    for _ in range(100):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=(random.randint(100, 200), random.randint(100, 200), random.randint(100, 200)))

    # 绘制验证码文字
    try:
        font = ImageFont.truetype("arial.ttf", 38)
    except:
        font = ImageFont.load_default()

    for i, char in enumerate(code):
        x = 20 + i * 35
        y = random.randint(5, 15)
        color = (random.randint(0, 100), random.randint(0, 100), random.randint(0, 100))
        draw.text((x, y), char, fill=color, font=font)

    # 转为 Base64（只返回纯 base64，前端会拼接前缀）
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG')
    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    return success({
        "uuid": captcha_id,
        "img": img_base64,
        "captchaEnabled": True,
    })


class LoginRequest(BaseModel):
    username: str
    password: str
    code: Optional[str] = None
    uuid: Optional[str] = None


class RegisterRequest(BaseModel):
    username: str
    password: str
    nick_name: Optional[str] = None


@router.post("/login")
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录"""
    # 查询验证码开关配置
    config_query = select(SysConfig).where(SysConfig.config_key == "sys.account.captchaEnabled")
    config_result = await db.execute(config_query)
    captcha_config = config_result.scalar_one_or_none()
    captcha_enabled = captcha_config.config_value.lower() == "true" if captcha_config else True

    # 验证码校验（仅在开启时强制验证）
    if captcha_enabled:
        if not data.code or not data.uuid:
            return error("请输入验证码")
        cached_code = await get_cache(f"captcha:{data.uuid}")
        if not cached_code or cached_code.lower() != data.code.lower():
            return error("验证码错误")

    # 查询用户
    user_repo = UserRepository(db)
    user = await user_repo.get_by_username(data.username)

    if not user:
        return error("用户不存在")

    if user.status != "0":
        return error("账号已被停用")

    # 验证密码
    if not verify_password(data.password, user.password):
        return error("密码错误")

    # 获取用户角色和权限
    roles = await user_repo.get_user_roles(user.user_id)
    perms = await user_repo.get_user_permissions(user.user_id)

    # 创建 Token
    token = await create_login_token(
        user_id=user.user_id,
        user_name=user.user_name,
        nick_name=user.nick_name,
        roles=[r.role_key for r in roles],
        perms=perms,
    )

    return success({"token": token})


# ========== 演示账号一键登录 ==========
# 仅用于功能演示：只放行下列白名单账号，不接受任意用户名，也不校验密码/验证码。
# 演示账号由 seed_demo_users.py 创建。
DEMO_ACCOUNTS = {
    "user1": "user1",
    "user2": "user2",
    "admin": "admin",
    "guest": "guest",
}


class QuickLoginRequest(BaseModel):
    account: str


@router.post("/quickLogin")
async def quick_login(data: QuickLoginRequest, db: AsyncSession = Depends(get_db)):
    """演示用一键登录（白名单账号，免密码免验证码）

    :param account: user1 / user2 / admin / guest
    """
    key = (data.account or "").strip().lower()
    username = DEMO_ACCOUNTS.get(key)
    if not username:
        return error("不支持的演示账号")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_username(username)
    if not user:
        return error("演示账号不存在，请先执行 openstudy-fastapi/seed_demo_users.py 初始化演示数据")

    if user.status != "0":
        return error("账号已被停用")

    roles = await user_repo.get_user_roles(user.user_id)
    perms = await user_repo.get_user_permissions(user.user_id)

    token = await create_login_token(
        user_id=user.user_id,
        user_name=user.user_name,
        nick_name=user.nick_name,
        roles=[r.role_key for r in roles],
        perms=perms,
    )

    return success({
        "token": token,
        "account": key,
        "userName": user.user_name,
        "nickName": user.nick_name,
    })


@router.post("/register")
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """用户注册"""
    user_repo = UserRepository(db)

    # 检查用户名是否已存在
    existing = await user_repo.get_by_username(data.username)
    if existing:
        return error("用户名已存在")

    # 创建用户
    from app.models.user import SysUser
    user = SysUser(
        user_name=data.username,
        nick_name=data.nick_name or data.username,
        password=hash_password(data.password),
    )
    await user_repo.create(user)

    return success({"user_id": user.user_id})


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """退出登录"""
    # 需要从请求中获取 token，这里简化处理
    return success("退出成功")


@router.get("/getInfo")
async def get_info(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """获取用户信息"""
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(current_user["user_id"])

    if not user:
        return error("用户不存在")

    roles = await user_repo.get_user_roles(user.user_id)
    perms = await user_repo.get_user_permissions(user.user_id)

    return success({
        "user": {
            "userId": user.user_id,
            "userName": user.user_name,
            "nickName": user.nick_name,
            "email": user.email,
            "phonenumber": user.phonenumber,
            "sex": user.sex,
            "avatar": user.avatar,
            "status": user.status,
        },
        "roles": [r.role_key for r in roles],
        "permissions": perms,
    })


@router.get("/getRouters")
async def get_routers(current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """获取路由菜单"""
    # 返回基础路由结构
    routers = [
        {
            "name": "System",
            "path": "/system",
            "hidden": False,
            "redirect": "noRedirect",
            "component": "Layout",
            "alwaysShow": True,
            "meta": {"title": "系统管理", "icon": "system", "noCache": False, "link": None},
            "children": [
                {
                    "name": "User",
                    "path": "user",
                    "hidden": False,
                    "component": "system/user/index",
                    "meta": {"title": "用户管理", "icon": "user", "noCache": False, "link": None}
                },
                {
                    "name": "Config",
                    "path": "config",
                    "hidden": False,
                    "component": "system/config/index",
                    "meta": {"title": "参数管理", "icon": "edit", "noCache": False, "link": None}
                },
                {
                    "name": "Notice",
                    "path": "notice",
                    "hidden": False,
                    "component": "system/notice/index",
                    "meta": {"title": "通知公告", "icon": "message", "noCache": False, "link": None}
                }
            ]
        },
    ]
    return success(routers)
