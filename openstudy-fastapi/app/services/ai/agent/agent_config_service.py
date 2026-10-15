"""
用户自定义智能体的读写服务（`ai_agent_config`）

产品口径
--------
用户能自己创建 / 命名 / 保存智能体（人设提示词 + 工具白名单 + 可选模型），
用于复用自己的 AI 工作流（如「数学老师」「英语助教」）。

本模块**自己开数据库会话**（调用方不持有 db）—— 与 `tool_pref_service` 同一理由：
这些读写会发生在**流式响应**里（编排层解析用户 Agent），借请求会话会漏连接
（见 `runtime_context` 的实测说明）。

鉴权口径（红线）
----------------
所有「按 id 操作」的入口都把 `user_id` 写进 SQL 的 WHERE 里（**不在调用方**）——
一次漏判就是 IDOR（拿别人的 id 读写数据）。返回 `None` 表示「不存在或不属于你」，
调用方据此回 404/403，**绝不**区分二者（区分等于泄露「这个 id 存在」）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import func, select

from app.database import async_session_factory
from app.models.agent_config import (
    DEL_FLAG_DELETED,
    DEL_FLAG_NORMAL,
    MAX_AGENTS_PER_USER,
    MAX_NAME_LEN,
    MAX_PERSONA_LEN,
    AiAgentConfig,
)


class AgentConfigError(Exception):
    """业务错误（名字冲突 / 超额度 / 非法字段）—— 调用方转成 400。"""


def to_dict(row: AiAgentConfig) -> Dict[str, Any]:
    """ORM → 前端友好形状（camelCase，与项目其他接口一致）"""
    return {
        "agentId": row.id,
        "name": row.name,
        "description": row.description or "",
        "greeting": row.greeting or "",
        "personaPrompt": row.persona_prompt or "",
        "tools": list(row.tools or []),
        "model": row.model or "",
        "isEnabled": int(row.is_enabled or 0),
        "createTime": row.create_time.isoformat(sep=" ") if row.create_time else None,
        "updateTime": row.update_time.isoformat(sep=" ") if row.update_time else None,
    }


def _normalize_tools(tools: Any) -> Optional[List[str]]:
    """把工具白名单归一成 `list[str]`（去空、去重、保序）；None/空 → None（= 不限）。"""
    if tools is None:
        return None
    if isinstance(tools, str):
        candidates = [p.strip() for p in tools.replace("，", ",").split(",")]
    elif isinstance(tools, (list, tuple, set)):
        candidates = [str(p).strip() for p in tools]
    else:
        candidates = []
    seen: List[str] = []
    for name in candidates:
        if name and name not in seen:
            seen.append(name)
    return seen or None


async def list_agents(user_id: int, *, include_disabled: bool = False) -> List[Dict[str, Any]]:
    """列出该用户的智能体（默认不含已暂停的；**永不抛**，读失败返回空表）。"""
    uid = int(user_id or 0)
    if uid <= 0:
        return []
    try:
        async with async_session_factory() as db:
            conds = [
                AiAgentConfig.user_id == uid,
                AiAgentConfig.del_flag == DEL_FLAG_NORMAL,
            ]
            if not include_disabled:
                conds.append(AiAgentConfig.is_enabled == 1)
            rows = (
                await db.execute(
                    select(AiAgentConfig).where(*conds).order_by(AiAgentConfig.id.desc())
                )
            ).scalars().all()
            return [to_dict(r) for r in rows]
    except Exception as e:  # noqa: BLE001 - 读失败 fail-open（同 tool_pref_service 的方向）
        logger.warning("[agent_config] 列出智能体失败（返回空）user={}: {}", uid, e)
        return []


async def get_agent(user_id: int, agent_id: int) -> Optional[AiAgentConfig]:
    """按 id 取（**归属写进 SQL**）；不存在或不属于该用户返回 None。"""
    uid = int(user_id or 0)
    aid = int(agent_id or 0)
    if uid <= 0 or aid <= 0:
        return None
    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(AiAgentConfig).where(
                    AiAgentConfig.id == aid,
                    AiAgentConfig.user_id == uid,
                    AiAgentConfig.del_flag == DEL_FLAG_NORMAL,
                )
            )
        ).scalars().first()
        return row


async def get_agent_dict(user_id: int, agent_id: int) -> Optional[Dict[str, Any]]:
    """按 id 取并转 dict（供编排层消费：人设 / 工具 / 模型）。"""
    row = await get_agent(user_id, agent_id)
    return to_dict(row) if row is not None else None


async def create_agent(
    user_id: int,
    *,
    name: str,
    persona_prompt: str = "",
    description: str = "",
    greeting: str = "",
    tools: Any = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """新建智能体。名字冲突 / 超额度 → 抛 `AgentConfigError`（**写失败必须抛**）。"""
    uid = int(user_id or 0)
    if uid <= 0:
        raise AgentConfigError("未登录")
    nm = str(name or "").strip()
    if not nm:
        raise AgentConfigError("智能体名称不能为空")
    if len(nm) > MAX_NAME_LEN:
        raise AgentConfigError(f"名称过长（上限 {MAX_NAME_LEN} 字）")
    persona = str(persona_prompt or "").strip()
    if len(persona) > MAX_PERSONA_LEN:
        raise AgentConfigError(f"人设提示词过长（上限 {MAX_PERSONA_LEN} 字）")

    async with async_session_factory() as db:
        # 额度闸门
        total = (
            await db.execute(
                select(func.count()).select_from(AiAgentConfig).where(
                    AiAgentConfig.user_id == uid,
                    AiAgentConfig.del_flag == DEL_FLAG_NORMAL,
                )
            )
        ).scalar() or 0
        if int(total) >= MAX_AGENTS_PER_USER:
            raise AgentConfigError(f"智能体数量已达上限（{MAX_AGENTS_PER_USER} 个）")

        # 名字唯一（同用户下）
        dup = (
            await db.execute(
                select(AiAgentConfig.id).where(
                    AiAgentConfig.user_id == uid,
                    AiAgentConfig.name == nm,
                    AiAgentConfig.del_flag == DEL_FLAG_NORMAL,
                )
            )
        ).first()
        if dup is not None:
            raise AgentConfigError(f"已存在名为「{nm}」的智能体，请换一个名字")

        now = datetime.now()
        row = AiAgentConfig(
            user_id=uid,
            name=nm,
            description=str(description or "").strip() or None,
            greeting=str(greeting or "").strip() or None,
            persona_prompt=persona or None,
            tools=_normalize_tools(tools),
            model=(str(model).strip() or None) if model else None,
            is_enabled=1,
            del_flag=DEL_FLAG_NORMAL,
            create_time=now,
            update_time=now,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return to_dict(row)


async def update_agent(
    user_id: int,
    agent_id: int,
    *,
    name: Optional[str] = None,
    persona_prompt: Optional[str] = None,
    description: Optional[str] = None,
    greeting: Optional[str] = None,
    tools: Any = None,
    model: Optional[str] = None,
    is_enabled: Optional[int] = None,
) -> Dict[str, Any]:
    """更新智能体（归属写进 SQL）。不存在或不属于该用户 → 抛 `AgentConfigError`。"""
    uid = int(user_id or 0)
    aid = int(agent_id or 0)
    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(AiAgentConfig).where(
                    AiAgentConfig.id == aid,
                    AiAgentConfig.user_id == uid,
                    AiAgentConfig.del_flag == DEL_FLAG_NORMAL,
                )
            )
        ).scalars().first()
        if row is None:
            raise AgentConfigError("智能体不存在或无权访问")

        if name is not None:
            nm = str(name).strip()
            if not nm:
                raise AgentConfigError("智能体名称不能为空")
            if len(nm) > MAX_NAME_LEN:
                raise AgentConfigError(f"名称过长（上限 {MAX_NAME_LEN} 字）")
            if nm != row.name:
                dup = (
                    await db.execute(
                        select(AiAgentConfig.id).where(
                            AiAgentConfig.user_id == uid,
                            AiAgentConfig.name == nm,
                            AiAgentConfig.del_flag == DEL_FLAG_NORMAL,
                            AiAgentConfig.id != aid,
                        )
                    )
                ).first()
                if dup is not None:
                    raise AgentConfigError(f"已存在名为「{nm}」的智能体，请换一个名字")
            row.name = nm

        if persona_prompt is not None:
            persona = str(persona_prompt).strip()
            if len(persona) > MAX_PERSONA_LEN:
                raise AgentConfigError(f"人设提示词过长（上限 {MAX_PERSONA_LEN} 字）")
            row.persona_prompt = persona or None
        if description is not None:
            row.description = str(description).strip() or None
        if greeting is not None:
            row.greeting = str(greeting).strip() or None
        if tools is not None:
            row.tools = _normalize_tools(tools)
        if model is not None:
            row.model = str(model).strip() or None
        if is_enabled is not None:
            row.is_enabled = 1 if int(is_enabled) else 0

        row.update_time = datetime.now()
        await db.commit()
        await db.refresh(row)
        return to_dict(row)


async def delete_agent(user_id: int, agent_id: int) -> Dict[str, Any]:
    """逻辑删除智能体（归属写进 SQL）。返回被删对象的 dict（供回执文案）。"""
    uid = int(user_id or 0)
    aid = int(agent_id or 0)
    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(AiAgentConfig).where(
                    AiAgentConfig.id == aid,
                    AiAgentConfig.user_id == uid,
                    AiAgentConfig.del_flag == DEL_FLAG_NORMAL,
                )
            )
        ).scalars().first()
        if row is None:
            raise AgentConfigError("智能体不存在或无权访问")
        info = to_dict(row)
        row.del_flag = DEL_FLAG_DELETED
        row.update_time = datetime.now()
        await db.commit()
        return info


__all__ = [
    "AgentConfigError",
    "list_agents",
    "get_agent",
    "get_agent_dict",
    "create_agent",
    "update_agent",
    "delete_agent",
    "to_dict",
]
