"""
基于 sys_ai_config 表的 AI 配置服务
所有 AI 调用统一从表里解析模型配置（model / api_key / base_url），
provider 为空时使用表中 is_default=1 的系统默认模型。
"""

from typing import List, Optional, AsyncIterator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from loguru import logger

from app.models.ai_config import SysAiConfig
from app.services.ai.base_client import ChatMessage, ChatResponse
from app.services.ai.dynamic_ai import dynamic_ai
from app.config import settings

# provider 未配置 base_url 时的默认 API 地址（OpenAI 兼容）
PROVIDER_BASE_URLS = {
    "deepseek": "https://api.deepseek.com/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "siliconflow": "https://api.siliconflow.cn/v1",
}


async def get_default_config(db: AsyncSession) -> Optional[SysAiConfig]:
    """获取系统默认模型配置（is_default=1 且启用）"""
    result = await db.execute(
        select(SysAiConfig)
        .where(SysAiConfig.is_default == 1, SysAiConfig.is_enabled == 1)
        .order_by(SysAiConfig.config_id.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_config_by_provider(db: AsyncSession, provider: str) -> Optional[SysAiConfig]:
    """按 provider 获取启用的模型配置（优先默认）"""
    result = await db.execute(
        select(SysAiConfig)
        .where(SysAiConfig.provider == provider, SysAiConfig.is_enabled == 1)
        .order_by(SysAiConfig.is_default.desc(), SysAiConfig.config_id.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_enabled_configs(db: AsyncSession) -> List[SysAiConfig]:
    """获取所有启用的模型配置"""
    result = await db.execute(
        select(SysAiConfig)
        .where(SysAiConfig.is_enabled == 1)
        .order_by(SysAiConfig.is_default.desc(), SysAiConfig.config_id.asc())
    )
    return list(result.scalars().all())


async def resolve_config(db: AsyncSession, provider: Optional[str]) -> Optional[SysAiConfig]:
    """解析模型配置：provider 为空 → 系统默认；否则按 provider 查表"""
    if provider:
        return await get_config_by_provider(db, provider)
    return await get_default_config(db)


def _to_lc_messages(messages: List[ChatMessage]) -> list:
    lc_messages = []
    for msg in messages:
        if msg.role == "system":
            lc_messages.append(SystemMessage(content=msg.content))
        elif msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            lc_messages.append(AIMessage(content=msg.content))
    return lc_messages


def _resolve_thinking(config: SysAiConfig, thinking: Optional[bool]) -> Optional[bool]:
    """决定本次请求是否开启「深度思考」。

    优先级：
    1. `thinking` 显式传入（前端开关）→ 直接生效
    2. 否则读 `config.thinking_mode`：
       - disabled/off/false/0/no  → False（关闭）
       - enabled/on/true/1/yes    → True（开启）
       - auto / 空 / 其它         → None（不传参，跟随模型默认行为）
    """
    if thinking is not None:
        return thinking
    mode = (config.thinking_mode or "").strip().lower()
    if mode in ("disabled", "off", "false", "0", "no"):
        return False
    if mode in ("enabled", "on", "true", "1", "yes"):
        return True
    return None


def _build_llm(
    config: SysAiConfig,
    temperature: float = 0.7,
    max_tokens: int = 8000,
    thinking: Optional[bool] = None,
) -> ChatOpenAI:
    """根据表配置动态构建 OpenAI 兼容客户端（支持深度思考开关）

    深度思考通过 `extra_body` 透传（DeepSeek 兼容参数）：
    - 开启：{"thinking": {"type": "enabled"}, "reasoning_effort": <配置值>}
    - 关闭：{"thinking": {"type": "disabled"}}
    - 跟随默认：不传，交给模型自己决定
    """
    base_url = (config.base_url or "").strip() or PROVIDER_BASE_URLS.get(config.provider) or "https://api.deepseek.com/v1"

    extra_body: dict = {}
    resolved = _resolve_thinking(config, thinking)
    if resolved is True:
        extra_body["thinking"] = {"type": "enabled"}
        effort = (config.reasoning_effort or "").strip()
        if effort:
            extra_body["reasoning_effort"] = effort
    elif resolved is False:
        extra_body["thinking"] = {"type": "disabled"}

    kwargs = dict(
        model=config.model,
        temperature=temperature,
        max_tokens=max_tokens,
        openai_api_key=config.api_key or settings.DEEPSEEK_API_KEY,
        openai_api_base=base_url,
    )
    if extra_body:
        kwargs["extra_body"] = extra_body
        logger.info(f"[db_config] thinking resolved={resolved}, extra_body={extra_body}")
    return ChatOpenAI(**kwargs)


async def stream_with_config(
    db: AsyncSession,
    messages: List[ChatMessage],
    provider: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 8000,
    thinking: Optional[bool] = None,
) -> AsyncIterator[str]:
    """流式输出：优先使用 sys_ai_config 表配置；表无配置时回退内置 dynamic_ai 路由

    注意：这里**只输出正式回答（content）**，深度思考的 reasoning_content 会被丢弃，
    前端用「思考中」动画来占位即可。
    """
    config = await resolve_config(db, provider)
    if config:
        logger.info(f"[db_config] Using table config: provider={config.provider}, model={config.model}")
        llm = _build_llm(config, temperature, max_tokens, thinking)
        async for chunk in llm.astream(_to_lc_messages(messages)):
            # 只转发正式回答；reasoning_content 不输出
            if chunk.content:
                yield chunk.content
        return

    # 回退：内置注册的客户端（provider 可能为 None，走默认 provider）
    logger.info(f"[db_config] No table config for provider={provider}, fallback to dynamic_ai")
    async for chunk in dynamic_ai.chat_stream(
        messages, model="deepseek-chat", provider=provider, temperature=temperature
    ):
        yield chunk


async def chat_with_config(
    db: AsyncSession,
    messages: List[ChatMessage],
    provider: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 8000,
    thinking: Optional[bool] = None,
) -> ChatResponse:
    """非流式输出：优先使用 sys_ai_config 表配置"""
    config = await resolve_config(db, provider)
    if config:
        logger.info(f"[db_config] Using table config: provider={config.provider}, model={config.model}")
        llm = _build_llm(config, temperature, max_tokens, thinking)
        response = await llm.ainvoke(_to_lc_messages(messages))
        return ChatResponse(content=response.content)

    response = await dynamic_ai.chat(
        messages, model="deepseek-chat", provider=provider, temperature=temperature
    )
    return response
