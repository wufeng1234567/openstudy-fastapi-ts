"""
AI 模型配置管理 API（sys_ai_config 表）
后台管理页面 /system/ai/config 使用；同时提供系统默认模型查询。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, update, delete as sa_delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import httpx

from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, error
from app.models.ai_config import SysAiConfig
from app.services.ai import db_config
from app.services.ai import context_budget

router = APIRouter()


# ---------- 权限与归属 ----------


def _is_admin(current_user: dict) -> bool:
    """是否管理员：roles 含 admin 系列，或权限含通配 `*:*:*`"""
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


def _own_scope(owner_id: Optional[int]):
    """「归属为 owner_id 的行」条件（None = 系统行）"""
    return SysAiConfig.user_id.is_(None) if not owner_id else SysAiConfig.user_id == owner_id


def _can_manage(cfg: SysAiConfig, current_user: dict) -> bool:
    """能否管理这条配置：管理员随意；普通用户只能动自己添加的"""
    if _is_admin(current_user):
        return True
    uid = _uid(current_user)
    return bool(uid and cfg.user_id == uid)


def format_config(cfg: SysAiConfig, mask_key: bool = False) -> dict:
    """同时返回两套字段命名，兼容不同前端页面（configId/model 与 modelId/modelName）

    source 字段区分两级来源：
      - "system"：系统提供（user_id 为空），如 deepseek 官方 / deepseek-free 官网 Web
      - "user"  ：用户自定义（user_id 有值）

    mask_key=True 时把 api_key 置空 —— 非管理员看**系统行**时用，
    避免任何登录用户都能从接口里读到官方 API Key（前端本来就只做展示掩码，
    掩码前的原值在响应体里明文可见）。
    ds-free 的密码字段一律只回传「是否已配置」。
    """
    return {
        "configId": cfg.config_id,
        "modelId": cfg.config_id,
        "userId": cfg.user_id,
        "source": "user" if cfg.user_id else "system",
        "provider": cfg.provider,
        "providerName": cfg.provider_name,
        "modelKind": cfg.model_kind,
        "model": cfg.model,
        "modelName": cfg.model,
        "apiKey": "" if mask_key else cfg.api_key,
        "baseUrl": cfg.base_url,
        "apiUrl": cfg.base_url,
        "isDefault": cfg.is_default,
        "isEnabled": cfg.is_enabled,
        "status": cfg.status,
        "remark": cfg.remark,
        "thinkingMode": cfg.thinking_mode,
        "reasoningEffort": cfg.reasoning_effort,
        "contextLength": cfg.context_length,
        # ds-free 专用：手机号可回传（便于确认账号），密码只回传是否已设置
        "webPhone": cfg.web_phone,
        "webAreaCode": cfg.web_area_code or "+86",
        "webPasswordSet": bool(cfg.web_password),
        "webPasswordMasked": "******" if cfg.web_password else "",
        "needsCredentials": cfg.provider == "deepseek-free",
        "createTime": cfg.create_time.isoformat() if cfg.create_time else None,
        "updateTime": cfg.update_time.isoformat() if cfg.update_time else None,
    }


class AiConfigBody(BaseModel):
    modelId: Optional[int] = None
    configId: Optional[int] = None
    provider: Optional[str] = None
    providerName: Optional[str] = None
    # 官方 / 中转站（Tab 决定）；落库字段为 sys_ai_config.model_kind
    modelKind: Optional[str] = None
    modelName: Optional[str] = None
    model: Optional[str] = None
    apiUrl: Optional[str] = None
    baseUrl: Optional[str] = None
    apiKey: Optional[str] = None
    isDefault: Optional[int] = None
    isEnabled: Optional[int] = 1
    status: Optional[str] = "0"
    remark: Optional[str] = None
    thinkingMode: Optional[str] = None
    reasoningEffort: Optional[str] = None
    contextLength: Optional[str] = None
    # ds-free（provider='deepseek-free'）专用凭据
    webPhone: Optional[str] = None
    webPassword: Optional[str] = None
    webAreaCode: Optional[str] = None


# ========== 查询类（注册在 /{config_id} 之前避免路径冲突） ==========


@router.get("/system/ai/config/context-presets")
async def list_context_presets(
    current_user: dict = Depends(get_current_user),
):
    """上下文长度档位清单（供前端下拉渲染，与后端预算口径同源）

    口径见 `app/services/ai/context_budget.py`：`context_length` 存的是
    「应用层喂多少历史进去」的预算，**不是**发给上游的参数（DeepSeek 官方
    没有上下文档位参数，两个模型窗口都是 1M）。
    """
    return success({
        "default": context_budget.DEFAULT_CONTEXT_LENGTH,
        "options": context_budget.preset_options(),
    })


@router.get("/system/ai/config/list")
async def list_ai_configs(
    scope: Optional[str] = Query(
        None,
        description="mine=仅我自己添加的模型；available=我可用的（系统 + 我的）；all=全部（仅管理员）",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询 AI 模型配置（按 scope 过滤可见范围）

    这个接口同时服务三个页面，语义必须分开，否则「个人中心 → 我的模型」
    会把系统提供的官方模型也列出来（用户报过）：

      · 个人中心「我的模型」  → `scope=mine`（只列 user_id = 我 的行）
      · 聊天/出题的模型下拉框 → `scope=available`（系统行 + 我自己的行）
      · 后台 AI 模型配置页    → 不传（管理员 → 全部；普通用户 → 自动降级为 available）

    ⚠️ 非管理员**永远拿不到 all**：否则能读到别人的自定义模型（及其 API Key）。
    非管理员看到的系统行 api_key 一律置空（前端本来就只做展示掩码）。
    """
    admin = _is_admin(current_user)
    uid = _uid(current_user)

    scope_key = (scope or "").strip().lower()
    if scope_key not in ("mine", "available", "all"):
        scope_key = "all" if admin else "available"
    if scope_key == "all" and not admin:
        scope_key = "available"

    stmt = select(SysAiConfig)
    if scope_key == "mine":
        if not uid:
            return {"code": 200, "msg": "操作成功", "rows": [], "data": [], "total": 0}
        stmt = stmt.where(SysAiConfig.user_id == uid)
    elif scope_key == "available":
        stmt = stmt.where(
            or_(SysAiConfig.user_id.is_(None), SysAiConfig.user_id == uid) if uid
            else SysAiConfig.user_id.is_(None)
        )

    result = await db.execute(
        stmt.order_by(
            SysAiConfig.is_default.desc(),
            SysAiConfig.user_id.desc(),
            SysAiConfig.config_id.asc(),
        )
    )
    configs = list(result.scalars().all())
    data = [
        format_config(c, mask_key=(not admin and c.user_id != uid))
        for c in configs
    ]
    # rows 兼容 AiModelSelector/AiModelManager，data 兼容后台管理页
    return {"code": 200, "msg": "操作成功", "rows": data, "data": data, "total": len(data)}


@router.get("/system/ai/config/current")
async def get_current_model(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取当前默认模型（当前用户视角：自己的默认优先，其次系统默认）"""
    cfg = await db_config.get_default_config(db, _uid(current_user))
    if not cfg:
        return error("未设置默认模型，请在后台 AI 管理页面设置")
    return success(format_config(cfg, mask_key=not _is_admin(current_user)))


@router.get("/system/ai/config/effective")
async def get_effective_config(
    provider: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取生效配置（provider 为空时取默认）"""
    uid = _uid(current_user)
    cfg = await db_config.resolve_config(db, provider, user_id=uid)
    if not cfg:
        return error("无可用模型配置")
    return success(format_config(cfg, mask_key=not _is_admin(current_user)))


@router.get("/system/ai/config/{config_id}")
async def get_ai_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询配置详情（非本人配置脱敏返回）"""
    cfg = await db.get(SysAiConfig, config_id)
    if not cfg:
        return error("配置不存在")
    return success(format_config(cfg, mask_key=not _can_manage(cfg, current_user)))


# ========== 写操作 ==========


@router.post("/system/ai/config")
async def add_ai_config(
    body: AiConfigBody,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """新增模型配置

    ⚠️ 归属规则（决定它出现在哪里）：
      · 管理员（后台页）创建 → `user_id = NULL` = **系统提供**，所有用户都能用；
      · 普通用户（个人中心 → 我的模型）创建 → `user_id = 自己` = **私有**，
        只对他自己可见可用。

    旧实现从不写 user_id → 用户自己加的模型变成「系统模型」：
    ① 在自己「我的模型」里因为按 source 过滤反而看不到；② 还会泄漏给所有人。
    """
    model = body.model or body.modelName
    if not model:
        return error("模型名称不能为空")
    if not body.provider:
        return error("供应商不能为空")

    admin = _is_admin(current_user)
    uid = _uid(current_user)
    if not admin and not uid:
        return error("无法识别当前用户，请重新登录后再试")
    owner_id = None if admin else uid

    # 设为默认前清除「同一 provider」下的其它默认标记。
    # ⚠️ 必须限定在**同一归属范围**内：否则普通用户把自己模型设默认时
    #    会把系统默认一并清掉（反之亦然），影响所有人。
    # （允许多个默认：系统提供的 ds 与 ds-free 可以各自是默认，互不顶掉）
    if body.isDefault == 1:
        await db.execute(
            update(SysAiConfig)
            .where(
                SysAiConfig.is_default == 1,
                SysAiConfig.provider == body.provider,
                _own_scope(owner_id),
            )
            .values(is_default=0)
        )

    cfg = SysAiConfig(
        user_id=owner_id,
        provider=body.provider,
        provider_name=body.providerName or body.provider,
        model_kind=body.modelKind,
        model=model,
        api_key=body.apiKey,
        base_url=body.baseUrl or body.apiUrl,
        web_phone=body.webPhone,
        web_password=body.webPassword,
        web_area_code=body.webAreaCode or "+86",
        is_default=1 if body.isDefault == 1 else 0,
        is_enabled=1 if body.isEnabled is None else body.isEnabled,
        status=body.status or "0",
        remark=body.remark,
        thinking_mode=body.thinkingMode,
        reasoning_effort=body.reasoningEffort,
        # 上下文档位落库前归一（非法值 / 旧值 32k|128k → 默认 200k）—— 见 context_budget
        context_length=context_budget.normalize_context_length(body.contextLength),
        create_time=datetime.now(),
        create_by=current_user.get("user_name", "admin"),
    )
    db.add(cfg)
    await db.commit()
    return success(format_config(cfg))


@router.put("/system/ai/config")
async def update_ai_config(
    body: AiConfigBody,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """修改模型配置（普通用户只能改自己添加的）"""
    config_id = body.modelId or body.configId
    if not config_id:
        return error("缺少配置ID")
    cfg = await db.get(SysAiConfig, config_id)
    if not cfg:
        return error("配置不存在")
    if not _can_manage(cfg, current_user):
        return error("无权修改该模型配置，只能修改自己在「我的模型」里添加的模型")

    if body.provider:
        cfg.provider = body.provider
    if body.providerName is not None:
        cfg.provider_name = body.providerName
    if body.modelKind is not None:
        cfg.model_kind = body.modelKind
    model = body.model or body.modelName
    if model:
        cfg.model = model
    if body.apiKey is not None:
        cfg.api_key = body.apiKey
    base_url = body.baseUrl or body.apiUrl
    if base_url is not None:
        cfg.base_url = base_url
    if body.isDefault is not None:
        if body.isDefault == 1:
            # 设为默认：先清除「同一 provider + 同一归属」下其它行的默认标记（排除自身）
            await db.execute(
                update(SysAiConfig)
                .where(
                    SysAiConfig.is_default == 1,
                    SysAiConfig.provider == cfg.provider,
                    SysAiConfig.config_id != config_id,
                    _own_scope(cfg.user_id),
                )
                .values(is_default=0)
            )
            cfg.is_default = 1
        elif cfg.is_default == 1:
            # 不允许直接取消该 provider 的唯一默认，需将同 provider 的其它模型设为默认来替换
            return error("不能取消当前默认模型，请将其它模型设为默认")
    if body.isEnabled is not None:
        if body.isEnabled != 1 and cfg.is_default == 1 and body.isDefault != 1:
            return error("默认模型不能停用，请先将其它模型设为默认")
        cfg.is_enabled = body.isEnabled
    if body.status is not None:
        cfg.status = body.status
    if body.remark is not None:
        cfg.remark = body.remark
    if body.thinkingMode is not None:
        cfg.thinking_mode = body.thinkingMode
    if body.reasoningEffort is not None:
        cfg.reasoning_effort = body.reasoningEffort
    if body.contextLength is not None:
        cfg.context_length = context_budget.normalize_context_length(body.contextLength)
    # ds-free 凭据：密码留空或传掩码表示「不修改」
    if body.webPhone is not None:
        cfg.web_phone = body.webPhone
    if body.webAreaCode is not None:
        cfg.web_area_code = body.webAreaCode
    if body.webPassword is not None and body.webPassword != "" and body.webPassword != "******":
        cfg.web_password = body.webPassword
    cfg.update_time = datetime.now()
    cfg.update_by = current_user.get("user_name", "admin")

    await db.commit()
    return success(format_config(cfg))


@router.put("/system/ai/config/default/{config_id}")
async def set_default_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """设置为默认模型：清除**同一归属范围**内的其它默认标记后设置该行

    普通用户只能把自己添加的模型设为「我的默认」，不会影响系统默认。
    """
    cfg = await db.get(SysAiConfig, config_id)
    if not cfg:
        return error("配置不存在")
    if not _can_manage(cfg, current_user):
        return error("无权操作该模型配置，只能操作自己在「我的模型」里添加的模型")
    if not cfg.is_enabled:
        return error("该配置已停用，无法设为默认")

    # 只清同一归属范围内的默认标记，再设置当前行
    await db.execute(
        update(SysAiConfig)
        .where(SysAiConfig.is_default == 1, _own_scope(cfg.user_id))
        .values(is_default=0)
    )
    cfg.is_default = 1
    cfg.update_time = datetime.now()
    cfg.update_by = current_user.get("user_name", "admin")
    await db.commit()

    return success(format_config(cfg))


@router.delete("/system/ai/config/{config_ids}")
async def delete_ai_config(
    config_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除模型配置（支持逗号分隔批量；普通用户只能删自己添加的）"""
    ids = [int(i) for i in config_ids.split(",") if i.strip().isdigit()]
    if not ids:
        return error("参数错误")

    rows = list(
        (await db.execute(select(SysAiConfig).where(SysAiConfig.config_id.in_(ids)))).scalars().all()
    )
    for cfg in rows:
        if not _can_manage(cfg, current_user):
            return error(f"无权删除模型配置「{cfg.model}」，只能删除自己在「我的模型」里添加的模型")

    # 不允许删除当前生效的默认配置（按调用者视角计算）
    default_cfg = await db_config.get_default_config(db, _uid(current_user))
    if default_cfg and default_cfg.config_id in ids:
        return error("默认模型不可删除，请先将其它模型设为默认")

    await db.execute(sa_delete(SysAiConfig).where(SysAiConfig.config_id.in_(ids)))
    await db.commit()
    return success()


@router.post("/system/ai/config/test")
async def test_ai_connection(
    body: AiConfigBody,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """测试模型连接

    - provider='deepseek-free'：走网页端反代链路，用手机号+密码登录真实试聊一次
    - 其它 provider：按 OpenAI 兼容格式请求 /chat/completions
    """
    from app.services.ai.db_config import PROVIDER_BASE_URLS

    cfg = None
    if body.modelId or body.configId:
        cfg = await db.get(SysAiConfig, body.modelId or body.configId)
        if not cfg:
            return error("配置不存在")
        if not _can_manage(cfg, current_user):
            return error("无权测试该模型配置，只能测试自己在「我的模型」里添加的模型")

    provider = body.provider or (cfg.provider if cfg else None)

    # ---- 分支一：ds-free 网页端反代 ----
    if provider == "deepseek-free":
        phone = body.webPhone or (cfg.web_phone if cfg else None)
        password = body.webPassword or ""
        # 掩码 / 空 → 用库里已存的密码
        if (not password or password == "******") and cfg:
            password = cfg.web_password or ""
        area_code = body.webAreaCode or (cfg.web_area_code if cfg else None) or "+86"

        if not phone or not password:
            return error("ds-free 需要手机号与密码，请在配置里填写")

        from app.services.ai.deepseek_web_client import DeepSeekWebClient

        client = DeepSeekWebClient(phone=phone, password=password, area_code=area_code)
        result = await client.self_test()
        if result.get("ok"):
            return success(result)
        return error(result.get("detail") or "ds-free 连通性测试失败")

    # ---- 分支二：OpenAI 兼容接口 ----
    if cfg:
        base_url = (body.apiUrl or body.baseUrl or cfg.base_url or "").strip()
        api_key = body.apiKey or cfg.api_key
        model = body.model or body.modelName or cfg.model
    else:
        base_url = (body.apiUrl or body.baseUrl or "").strip()
        api_key = body.apiKey
        model = body.model or body.modelName

    if not base_url:
        base_url = PROVIDER_BASE_URLS.get(provider, "https://api.deepseek.com/v1")
    url = base_url.rstrip("/") + "/chat/completions"

    try:
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 8,
                    "stream": False,
                },
            )
        if resp.status_code == 200:
            return success(f"模型 {model} 连接成功")
        return error(f"HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        return error(f"连接失败: {str(e)}")


@router.post("/system/ai/config/provider-models")
async def fetch_provider_models(
    body: AiConfigBody,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """拉取某 provider 的可用模型列表（OpenAI 兼容 GET /models）

    前端「AI 模型配置」页的「获取模型」按钮调用：
      - 传 apiKey + baseUrl（编辑场景可只传 configId，服务端复用库里的 Key）
      - 返回 { code, data: { models: [{id, ownedBy}], baseUrl } }
    用于让用户从下拉框里挑模型名，而不是手敲。
    """
    from app.services.ai.db_config import PROVIDER_BASE_URLS

    cfg = None
    if body.modelId or body.configId:
        cfg = await db.get(SysAiConfig, body.modelId or body.configId)
        if not cfg:
            return error("配置不存在")

    provider = body.provider or (cfg.provider if cfg else None)

    # ds-free 走网页端反代，没有标准 /models 列表，返回内置模型名
    if provider == "deepseek-free":
        return success({"models": [{"id": "ds-free-nb", "ownedBy": "deepseek-web"}], "baseUrl": ""})

    if cfg:
        base_url = (body.apiUrl or body.baseUrl or cfg.base_url or "").strip()
        api_key = body.apiKey or cfg.api_key
    else:
        base_url = (body.apiUrl or body.baseUrl or "").strip()
        api_key = body.apiKey

    if not base_url:
        base_url = PROVIDER_BASE_URLS.get(provider, "https://api.deepseek.com/v1")

    if not api_key:
        return error("请先填写 API Key")

    # ⚠️ SSRF 防护（2026-10-22）：base_url 由前端传入，若不校验，
    # 任何登录用户都能让服务端去请求内网地址（如 http://127.0.0.1:6379、
    # http://169.254.169.254/ 云元数据），用响应内容探测内网。
    # 这里只做「不能指向本机/内网」的最小校验，不限制具体域名
    # （用户确实可能用自己的中转站）。
    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        return error("API 地址必须以 http:// 或 https:// 开头")
    host = (parsed.hostname or "").lower()
    if not host:
        return error("API 地址缺少主机名")
    blocked = (
        host in ("localhost", "127.0.0.1", "0.0.0.0", "::1")
        or host.startswith("127.")
        or host.startswith("10.")
        or host.startswith("192.168.")
        or host.startswith("169.254.")
        or host.endswith(".local")
        or host.endswith(".internal")
    )
    if host.startswith("172."):
        try:
            second = int(host.split(".")[1])
            if 16 <= second <= 31:
                blocked = True
        except Exception:
            pass
    if blocked:
        return error("不允许请求本机或内网地址")

    url = base_url.rstrip("/") + "/models"
    try:
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code != 200:
            return error(f"HTTP {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        models = [
            {"id": m.get("id"), "ownedBy": m.get("owned_by")}
            for m in (payload.get("data") or [])
            if m.get("id")
        ]
        return success({"models": models, "baseUrl": base_url})
    except Exception as e:
        return error(f"获取模型列表失败: {str(e)}")
