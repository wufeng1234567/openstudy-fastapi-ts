"""
认证相关 API
"""

from fastapi import APIRouter, Depends, Request
from loguru import logger
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
    is_admin_user,
    remove_token,
)
from app.core.response import success, error
from app.repositories.user_repo import UserRepository
from app.services.audit_log_service import record_login
from app.utils.redis_util import get_cache, set_cache, delete_cache
from app.models.config import SysConfig
import uuid
import random
import string

router = APIRouter()


async def _demo_mode_enabled(db: AsyncSession) -> bool:
    """演示模式是否开启（`sys_config` 的 `sys.demo.mode`；缺配置时按**开启**兜底）

    ⚠️ 这是演示账号一键登录的**唯一开关**，`/captchaImage`（给前端决定显不显示按钮）与
    `/quickLogin`（决定放不放行）**必须读同一处**。原先 `/quickLogin` 完全不看这个开关 ——
    线上把演示模式关掉、登录页不显示按钮了，但接口仍可被直接 POST 免密登入任意演示账号
    （含 admin），是个越权口子。现在关掉 = 接口层也拒绝。
    """
    cfg = (await db.execute(
        select(SysConfig).where(SysConfig.config_key == "sys.demo.mode")
    )).scalar_one_or_none()
    return (cfg.config_value.lower() == "true") if cfg else True


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

    # 演示模式开关：true=保留「演示账号一键登录」入口（自用/演示）；
    # false=上线体验版，登录页默认走账号密码登录/注册，不暴露演示账号。
    # ⚠️ 与 `/quickLogin` 共用 `_demo_mode_enabled`，避免「前端藏了按钮、接口却仍放行」。
    demo_mode = await _demo_mode_enabled(db)

    captcha_id = str(uuid.uuid4())

    if not captcha_enabled:
        return success({
            "uuid": captcha_id,
            "img": "",
            "captchaEnabled": False,
            "demoMode": demo_mode,
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
    except Exception as exc:  # noqa: BLE001 - 字体缺失只影响验证码观感，可降级
        logger.warning("验证码字体加载失败，使用 PIL 默认字体: {}", exc)
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
        "demoMode": demo_mode,
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
async def login(
    data: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """用户登录（成功/失败都写 sys_logininfor）"""

    async def fail(msg: str):
        await record_login(
            db, user_name=data.username, status=1, msg=msg, request=request
        )
        return error(msg)

    # 查询验证码开关配置
    config_query = select(SysConfig).where(SysConfig.config_key == "sys.account.captchaEnabled")
    config_result = await db.execute(config_query)
    captcha_config = config_result.scalar_one_or_none()
    captcha_enabled = captcha_config.config_value.lower() == "true" if captcha_config else True

    # 验证码校验（仅在开启时强制验证）
    if captcha_enabled:
        if not data.code or not data.uuid:
            return await fail("请输入验证码")
        cached_code = await get_cache(f"captcha:{data.uuid}")
        if not cached_code or cached_code.lower() != data.code.lower():
            return await fail("验证码错误")

    # 查询用户
    user_repo = UserRepository(db)
    user = await user_repo.get_by_username(data.username)

    if not user:
        return await fail("用户不存在")

    if user.status != "0":
        return await fail("账号已被停用")

    # 验证密码
    if not verify_password(data.password, user.password):
        return await fail("密码错误")

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
    await record_login(
        db, user_name=user.user_name, status=0, msg="登录成功", request=request
    )

    return success({"token": token})


# ========== 演示账号一键登录 ==========
# 仅用于功能演示：只放行下列白名单账号，不接受任意用户名，也不校验密码/验证码。
# 演示账号由 seed_demo_users.py 创建。
DEMO_ACCOUNTS = {
    "user1": "user1",
    "user2": "user2",
    "guest": "guest",
}


class QuickLoginRequest(BaseModel):
    account: str


@router.post("/quickLogin")
async def quick_login(
    data: QuickLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """演示用一键登录（白名单账号，免密码免验证码）

    :param account: user1 / user2 / guest

    ⚠️ **演示模式关闭时直接拒绝**（见 `_demo_mode_enabled`）：否则线上关掉演示模式后，
    接口仍可被直接调用绕过登录。前端按钮的显隐由 `/captchaImage` 的 `demoMode` 决定，
    但那只是 UI；真正的门在这里。
    """
    if not await _demo_mode_enabled(db):
        return error("演示模式未开启")

    key = (data.account or "").strip().lower()
    username = DEMO_ACCOUNTS.get(key)
    if not username:
        return error("不支持的演示账号")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_username(username)
    if not user:
        return error("演示账号不存在，请先导入 deploy/db-init/97_demo_seed.sql 初始化演示数据")

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
    await record_login(
        db, user_name=user.user_name, status=0, msg="演示账号登录成功", request=request
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
async def logout(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """退出登录

    2026-10-28 修复：原来只回 success，**从不删除 Redis 里的登录 token** ——
    前端删了本地 token，但旧 token 在服务端仍有效至过期（且每次访问还会被
    `get_current_user` 的 `refresh_token` 续期）。这里从 Authorization 头
    提取 Bearer token 并调用 `remove_token` 真正注销（单点 token 一并清除）。
    """
    auth_header = request.headers.get("authorization") or ""
    token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
    if token:
        await remove_token(token)
    await record_login(
        db,
        user_name=str(current_user.get("user_name") or ""),
        status=0,
        msg="退出成功",
        request=request,
    )
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
    """按 `sys_menu` 返回当前用户可见的后台路由。

    原实现硬编码只返回 3 个系统页 + 1 个限流页，导致数据库里已有的
    角色/部门/菜单/监控等页面点击全部 404。现在管理员读取完整菜单表；
    普通用户仍不返回任何后台入口（前台导航是前端静态路由）。
    """
    if not is_admin_user(current_user):
        return success([])

    from app.models.menu import SysMenu
    menus = list(
        (
            await db.execute(
                select(SysMenu)
                .where(SysMenu.status == "0", SysMenu.menu_type.in_(["M", "C"]))
                .order_by(SysMenu.parent_id, SysMenu.order_num, SysMenu.menu_id)
            )
        ).scalars().all()
    )
    by_parent: dict = {}
    for m in menus:
        by_parent.setdefault(int(m.parent_id or 0), []).append(m)

    def build(parent_id: int) -> list:
        result = []
        for m in by_parent.get(parent_id, []):
            children = build(int(m.menu_id))
            raw_path = m.path or f"menu{m.menu_id}"
            if parent_id == 0 and not raw_path.startswith("/"):
                raw_path = "/" + raw_path
            if m.menu_type == "M":
                item = {
                    "name": f"Dir{m.menu_id}",
                    "path": raw_path,
                    "hidden": m.visible != "0",
                    "redirect": "noRedirect",
                    "component": "Layout",
                    "alwaysShow": True,
                    "meta": {"title": m.menu_name, "icon": m.icon or "system", "noCache": False, "link": None},
                }
                if children:
                    item["children"] = children
            else:
                if not m.component:
                    continue
                item = {
                    "name": f"Menu{m.menu_id}",
                    "path": raw_path,
                    "hidden": m.visible != "0",
                    "component": m.component,
                    "meta": {
                        "title": m.menu_name,
                        "icon": m.icon or "system",
                        "noCache": m.is_cache != 1,
                        "link": None,
                    },
                }
                if m.query:
                    item["query"] = m.query
            result.append(item)
        return result

    return success(build(0))
