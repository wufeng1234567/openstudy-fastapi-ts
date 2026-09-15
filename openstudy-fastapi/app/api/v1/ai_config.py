"""
AI 模型配置管理 API（sys_ai_config 表）
后台管理页面 /system/ai/config 使用；同时提供系统默认模型查询。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, update, delete as sa_delete, func
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

router = APIRouter()


def format_config(cfg: SysAiConfig) -> dict:
    """同时返回两套字段命名，兼容不同前端页面（configId/model 与 modelId/modelName）"""
    return {
        "configId": cfg.config_id,
        "modelId": cfg.config_id,
        "userId": cfg.user_id,
        "provider": cfg.provider,
        "providerName": cfg.provider_name,
        "model": cfg.model,
        "modelName": cfg.model,
        "apiKey": cfg.api_key,
        "baseUrl": cfg.base_url,
        "apiUrl": cfg.base_url,
        "isDefault": cfg.is_default,
        "isEnabled": cfg.is_enabled,
        "status": cfg.status,
        "remark": cfg.remark,
        "thinkingMode": cfg.thinking_mode,
        "reasoningEffort": cfg.reasoning_effort,
        "contextLength": cfg.context_length,
        "createTime": cfg.create_time.isoformat() if cfg.create_time else None,
        "updateTime": cfg.update_time.isoformat() if cfg.update_time else None,
    }


class AiConfigBody(BaseModel):
    modelId: Optional[int] = None
    configId: Optional[int] = None
    provider: Optional[str] = None
    providerName: Optional[str] = None
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


# ========== 查询类（注册在 /{config_id} 之前避免路径冲突） ==========


@router.get("/system/ai/config/list")
async def list_ai_configs(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询所有 AI 模型配置"""
    result = await db.execute(
        select(SysAiConfig).order_by(SysAiConfig.is_default.desc(), SysAiConfig.config_id.asc())
    )
    configs = list(result.scalars().all())
    data = [format_config(c) for c in configs]
    # rows 兼容 AiModelSelector/AiModelManager，data 兼容后台管理页
    return {"code": 200, "msg": "操作成功", "rows": data, "data": data, "total": len(data)}


@router.get("/system/ai/config/current")
async def get_current_model(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取当前系统默认模型"""
    cfg = await db_config.get_default_config(db)
    if not cfg:
        return error("未设置默认模型，请在后台 AI 管理页面设置")
    return success(format_config(cfg))


@router.get("/system/ai/config/effective")
async def get_effective_config(
    provider: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取生效配置（provider 为空时取系统默认）"""
    cfg = await db_config.resolve_config(db, provider)
    if not cfg:
        return error("无可用模型配置")
    return success(format_config(cfg))


@router.get("/system/ai/config/{config_id}")
async def get_ai_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询配置详情"""
    cfg = await db.get(SysAiConfig, config_id)
    if not cfg:
        return error("配置不存在")
    return success(format_config(cfg))


# ========== 写操作 ==========


@router.post("/system/ai/config")
async def add_ai_config(
    body: AiConfigBody,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """新增模型配置"""
    model = body.model or body.modelName
    if not model:
        return error("模型名称不能为空")
    if not body.provider:
        return error("供应商不能为空")

    # 设为默认前清除其它默认标记（保证全表唯一默认）
    if body.isDefault == 1:
        await db.execute(
            update(SysAiConfig).where(SysAiConfig.is_default == 1).values(is_default=0)
        )

    cfg = SysAiConfig(
        provider=body.provider,
        provider_name=body.providerName or body.provider,
        model=model,
        api_key=body.apiKey,
        base_url=body.baseUrl or body.apiUrl,
        is_default=1 if body.isDefault == 1 else 0,
        is_enabled=1 if body.isEnabled is None else body.isEnabled,
        status=body.status or "0",
        remark=body.remark,
        thinking_mode=body.thinkingMode,
        reasoning_effort=body.reasoningEffort,
        context_length=body.contextLength,
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
    """修改模型配置"""
    config_id = body.modelId or body.configId
    if not config_id:
        return error("缺少配置ID")
    cfg = await db.get(SysAiConfig, config_id)
    if not cfg:
        return error("配置不存在")

    if body.provider:
        cfg.provider = body.provider
    if body.providerName is not None:
        cfg.provider_name = body.providerName
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
            # 设为默认：先清除其它默认标记（排除自身）
            await db.execute(
                update(SysAiConfig)
                .where(SysAiConfig.is_default == 1, SysAiConfig.config_id != config_id)
                .values(is_default=0)
            )
            cfg.is_default = 1
        elif cfg.is_default == 1:
            # 不允许直接取消唯一默认，需将其它模型设为默认来替换
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
        cfg.context_length = body.contextLength
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
    """设置系统默认模型：清除其它默认标记后设置该行"""
    cfg = await db.get(SysAiConfig, config_id)
    if not cfg:
        return error("配置不存在")
    if not cfg.is_enabled:
        return error("该配置已停用，无法设为默认")

    # 清除所有默认标记，再设置当前行
    await db.execute(
        update(SysAiConfig).where(SysAiConfig.is_default == 1).values(is_default=0)
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
    """删除模型配置（支持逗号分隔批量）"""
    ids = [int(i) for i in config_ids.split(",") if i.strip().isdigit()]
    if not ids:
        return error("参数错误")

    # 不允许删除当前默认配置
    default_cfg = await db_config.get_default_config(db)
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
    """测试模型连接（优先用传入参数，否则查表）"""
    from app.services.ai.db_config import PROVIDER_BASE_URLS

    if body.modelId or body.configId:
        cfg = await db.get(SysAiConfig, body.modelId or body.configId)
        if not cfg:
            return error("配置不存在")
        base_url = (body.apiUrl or body.baseUrl or cfg.base_url or "").strip()
        api_key = body.apiKey or cfg.api_key
        model = body.model or body.modelName or cfg.model
    else:
        base_url = (body.apiUrl or body.baseUrl or "").strip()
        api_key = body.apiKey
        model = body.model or body.modelName

    if not base_url:
        base_url = PROVIDER_BASE_URLS.get(body.provider, "https://api.deepseek.com/v1")
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
