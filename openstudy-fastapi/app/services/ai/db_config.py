"""
基于 sys_ai_config 表的 AI 配置服务
所有 AI 调用统一从表里解析模型配置（model / api_key / base_url），
provider 为空时使用表中 is_default=1 的系统默认模型。
"""

from typing import Any, List, Optional, AsyncIterator
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from loguru import logger

from app.models.ai_config import SysAiConfig
from app.services.ai.base_client import ChatMessage, ChatResponse, to_lc_content, to_lc_text
from app.services.ai.dynamic_ai import dynamic_ai
from app.config import settings

# 让 LangChain 把流式分片里的 reasoning_content 透出来（原因见该模块 docstring：
# langchain-openai 的白名单转换会把它静默丢弃，导致深度思考链路根本读不到）。
# ⚠️ 必须在这里 import —— 本模块是**所有** LLM 的构造工厂，补丁在 import 时安装，
#    放别处容易出现「某条链路还没打上补丁就已经开始流式」的时序问题。
from app.services.ai import langchain_reasoning_patch as _reasoning_patch  # noqa: F401

# provider 未配置 base_url 时的默认 API 地址（OpenAI 兼容）
# DeepSeek 官方文档：base_url = https://api.deepseek.com（OpenAI 兼容）
#
# ⚠️ 键必须同时覆盖**前端配置表单里用的 provider 值**：前端「我的模型」表单
# 下拉给的是 `zhipuai` / `siliconflow` / `openai` / `deepseek`，而这里历史上有
# `zhipu`（没有 `zhipuai`）、也没有 `openai` —— 于是用户建智谱/OpenAI 模型时
# 只要留空 API 地址，就会被兜底成 DeepSeek 的地址，报一堆看不懂的错。
PROVIDER_BASE_URLS = {
    "deepseek": "https://api.deepseek.com",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "zhipuai": "https://open.bigmodel.cn/api/paas/v4",
    "siliconflow": "https://api.siliconflow.cn/v1",
    "openai": "https://api.openai.com/v1",
}

# ds-free（DeepSeek 官网 Web 版）由前端浏览器扩展代发请求，后端不能直接服务
DS_FREE_PROVIDER = "deepseek-free"


def _visible_scope(user_id: Optional[int]):
    """「这条配置对该用户可见」的 SQL 条件

    两级来源（与 `ai_config.format_config` 的 source 字段同一口径）：
      - `user_id IS NULL`  → **系统提供**（官方模型，所有登录用户可用）
      - `user_id = N`      → **用户自定义**（只属于 N，别人既看不到也用不到）

    ⚠️ `user_id=None`（没有登录上下文的老调用方 / 一次性生成场景）只允许系统行。
    旧实现按 `user_id.desc()` 排序却**不过滤**，等于「任意用户的自定义模型
    （与其 API Key）会顶掉系统行被他人用上」，是明确的越权隐患，此处一并收口。
    """
    if user_id:
        return or_(SysAiConfig.user_id.is_(None), SysAiConfig.user_id == user_id)
    return SysAiConfig.user_id.is_(None)


def _is_placeholder_key(key: str) -> bool:
    """判断 api_key 是不是「占位符」而非真 Key

    部署 SQL 里系统行默认写 `YOUR_API_KEY_HERE`，它**非空**但**不是真 Key**。
    旧实现只判空，占位符会通过 has_credentials 检查 → 后端拿它去调 API → 401。
    """
    k = (key or "").strip()
    if not k:
        return True
    lowered = k.lower()
    return (
        "your_api_key" in lowered
        or lowered in ("bridge", "changeme", "change-me", "placeholder", "todo")
        or lowered.startswith("your_")
    )


def has_credentials(config: SysAiConfig) -> bool:
    """这条配置有没有「能真正调用模型」的凭据

    - ds-free 走网页端反代，本来就不需要 API Key，永远算有凭据；
    - 其它 provider 必须有**真实的** api_key（排除占位符），或 .env 里的 DEEPSEEK_API_KEY。
    """
    if config.provider == DS_FREE_PROVIDER:
        return True
    api_key = (config.api_key or "").strip()
    if api_key and not _is_placeholder_key(api_key):
        return True
    env_key = (settings.DEEPSEEK_API_KEY or "").strip()
    return bool(env_key and not _is_placeholder_key(env_key))


def is_servable_by_backend(config: SysAiConfig) -> bool:
    """后端是否能直接服务这条配置（ds-free 由前端扩展处理 → 不能）"""
    return config.provider != DS_FREE_PROVIDER


def _no_credential_message(config: SysAiConfig) -> str:
    """「没有可用 API Key」时面向用户的**分场景**提示。

    区分系统行（官方模型）与用户自定义行，给不同的人不同的操作指引：
      - 系统行（user_id 为空）：这是**管理员**要处理的事，普通用户改不了 →
        提示联系管理员去后台配置；
      - 用户自定义行：是用户自己加的模型缺 Key → 提示去「我的模型」补全。
    """
    name = f"{config.provider_name or config.provider} · {config.model}"
    if config.user_id is None:
        return (
            f"系统官方模型「{name}」尚未配置 API Key，暂时无法使用。\n"
            "请联系【管理员】按以下步骤为官方模型配置密钥：\n"
            "  1. 用管理员账号登录，进入后台；\n"
            "  2. 打开「系统管理 → AI 模型配置」；\n"
            "  3. 找到该官方模型，填入有效的 API Key 并保存；\n"
            "  4. 回到对话页重试。\n"
            "（如果你是普通用户，也可以先到「个人中心 → 我的模型」添加自己的模型来使用。）"
        )
    return (
        f"你添加的模型「{name}」未填写有效的 API Key，无法调用。\n"
        "请到「个人中心 → 我的模型」里编辑该模型，填入有效的 API Key 后重试；"
        "或改用系统提供的官方模型。"
    )


async def get_default_config(
    db: AsyncSession, user_id: Optional[int] = None
) -> Optional[SysAiConfig]:
    """获取默认模型配置（is_default=1 且启用）

    可见范围：系统行 + 该用户自己的行；**用户自己设的默认优先于系统默认**
    （个人中心把自己的模型设为默认后，只有他自己会走这条）。

    ⚠️ 表里可能同时存在多条 is_default=1 的行（线上就出现过
    `deepseek-v4-flash` 与 `deepseek-free` 两条都是默认）。按 config_id 取第一条
    会选中「provider=deepseek 但 api_key 为空」的那条，于是每次对话都以
    `The api_key client option must be set` 失败，历史里只剩用户提问。

    这里改成：在默认行里优先挑「后端能直接服务且凭据齐全」的；一条都没有时
    仍然返回第一条（保持原有行为，让上层拿到明确报错而不是找不到配置）。
    """
    result = await db.execute(
        select(SysAiConfig)
        .where(
            SysAiConfig.is_default == 1,
            SysAiConfig.is_enabled == 1,
            _visible_scope(user_id),
        )
        .order_by(SysAiConfig.user_id.desc(), SysAiConfig.config_id.asc())
    )
    rows = list(result.scalars().all())

    # 先看「默认行」里有没有凭据齐全的；有就直接用
    for cfg in rows:
        if is_servable_by_backend(cfg) and has_credentials(cfg):
            if rows and cfg is not rows[0]:
                logger.warning(
                    "[db_config] 默认配置 config_id={} 不可用，改用 config_id={} provider={} model={}",
                    rows[0].config_id, cfg.config_id, cfg.provider, cfg.model,
                )
            return cfg

    # 默认行都不合格（比如系统默认行只是占位符 Key）→ 放宽到「任意启用且凭据齐全的行」，
    # 这样用户自己配了有效 Key 的模型（即使没设为默认）也能用起来。
    fallback = await db.execute(
        select(SysAiConfig)
        .where(SysAiConfig.is_enabled == 1, _visible_scope(user_id))
        .order_by(SysAiConfig.is_default.desc(), SysAiConfig.user_id.asc().nullsfirst(), SysAiConfig.config_id.asc())
    )
    for cfg in fallback.scalars().all():
        if is_servable_by_backend(cfg) and has_credentials(cfg):
            logger.warning(
                "[db_config] 无可用默认行，回退到有凭据的 config_id={} provider={} model={}",
                cfg.config_id, cfg.provider, cfg.model,
            )
            return cfg

    # 实在没有：返回默认行第一条（保持原行为，让上层拿到明确报错）
    if rows:
        return rows[0]
    return None


async def get_config_by_provider(
    db: AsyncSession, provider: str, user_id: Optional[int] = None
) -> Optional[SysAiConfig]:
    """按 provider 获取启用的模型配置（优先默认、其次凭据齐全）

    同一个 provider 在表里往往有多条（例如 provider=deepseek 有 3 条，
    只有其中一条填了 api_key）。原来只按 is_default desc 取第一条，会稳定选中
    那条空 Key 的默认行 —— 用户在模型下拉框里选了个「有 Key 的」也照样失败。
    这里改成：先按优先级排序，再取第一条凭据齐全的；全都没有则回退第一条。
    排序：系统默认行优先（官方），其次用户行；凭据是否有效由 for 循环判定。
    """
    result = await db.execute(
        select(SysAiConfig)
        .where(
            SysAiConfig.provider == provider,
            SysAiConfig.is_enabled == 1,
            _visible_scope(user_id),
        )
        .order_by(
            SysAiConfig.is_default.desc(),
            SysAiConfig.user_id.asc().nullsfirst(),
            SysAiConfig.config_id.asc(),
        )
    )
    rows = list(result.scalars().all())
    if not rows:
        return None

    for cfg in rows:
        if has_credentials(cfg):
            if cfg is not rows[0]:
                logger.warning(
                    "[db_config] provider={} 的首选配置 config_id={} 缺凭据，"
                    "改用 config_id={} model={}",
                    provider,
                    rows[0].config_id,
                    cfg.config_id,
                    cfg.model,
                )
            return cfg
    return rows[0]


async def get_config_by_model(
    db: AsyncSession, model: str, user_id: Optional[int] = None
) -> Optional[SysAiConfig]:
    """按模型名获取启用的模型配置（前端模型下拉框现在按 model 选择）

    同一个 model 名可能同时存在「系统提供」和「用户自定义」两行。
    选取优先级：**凭据齐全** > **用户自己的行** > 系统行。
    即：用户自己配了同名模型（有自己的 Key）时用它自己的，否则用系统的。
    这与前端下拉框「同名时用户组优先展示」的口径一致。
    别人的自定义行在这里被 `_visible_scope` 直接过滤掉。
    """
    result = await db.execute(
        select(SysAiConfig)
        .where(
            SysAiConfig.model == model,
            SysAiConfig.is_enabled == 1,
            _visible_scope(user_id),
        )
        .order_by(
            SysAiConfig.user_id.desc(),
            SysAiConfig.is_default.desc(),
            SysAiConfig.config_id.asc(),
        )
    )
    rows = list(result.scalars().all())
    if not rows:
        return None

    for cfg in rows:
        if is_servable_by_backend(cfg) and has_credentials(cfg):
            return cfg
    return rows[0]


async def get_enabled_configs(
    db: AsyncSession, user_id: Optional[int] = None
) -> List[SysAiConfig]:
    """获取对该用户可用的、已启用的模型配置（系统行 + 自己的行）"""
    result = await db.execute(
        select(SysAiConfig)
        .where(SysAiConfig.is_enabled == 1, _visible_scope(user_id))
        .order_by(
            SysAiConfig.user_id.desc(),
            SysAiConfig.is_default.desc(),
            SysAiConfig.config_id.asc(),
        )
    )
    return list(result.scalars().all())


async def resolve_config(
    db: AsyncSession,
    provider: Optional[str],
    model: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Optional[SysAiConfig]:
    """解析模型配置：model 优先（前端下拉框按模型选择）→ provider → 默认

    `user_id` 决定可见范围（系统行 + 自己的行）；不传则只用系统行。
    """
    if model:
        cfg = await get_config_by_model(db, model, user_id)
        if cfg:
            return cfg
    if provider:
        return await get_config_by_provider(db, provider, user_id)
    return await get_default_config(db, user_id)


def _to_lc_messages(messages: List[ChatMessage]) -> list:
    """ChatMessage → LangChain 消息

    ⚠️ 必须走 `to_lc_content()` 转换：带图片时 content 是
    `[TextBlock, ImageBlock]` 这样的 pydantic 块列表，而 LangChain 只接受
    `list[str | dict]`，直接塞会抛一串 validation errors（症状：纯文字正常、
    一并发图就「发送失败」）。system / assistant 一律压成纯文本。
    """
    lc_messages = []
    for msg in messages:
        if msg.role == "system":
            lc_messages.append(SystemMessage(content=to_lc_text(msg.content)))
        elif msg.role == "user":
            lc_messages.append(HumanMessage(content=to_lc_content(msg.content)))
        elif msg.role == "assistant":
            lc_messages.append(AIMessage(content=to_lc_text(msg.content)))
    return lc_messages


#: `_build_llm(thinking=...)` 的哨兵值 —— 明确表示「什么思考参数都不要发」。
#:
#: ⚠️ 不能用 `None` 代替：`None` 的既有语义是「去读 config.thinking_mode」，
#:    两者会撞车 —— Agent 模式想「不传」，却会被解析成「按配置关闭」，
#:    于是又发出 `{"thinking":{"type":"disabled"}}` 把思考掐掉（实测踩过）。
_OMIT_THINKING = object()


def _is_official_deepseek(config: SysAiConfig) -> bool:
    """这条配置是否是**官方 DeepSeek 域**（认得 `{"thinking":{"type":"enabled"}}` 专有形状）

    判据优先级：
    1. `model_kind == "official"` → 只看 provider 是否 deepseek 系（Tab 显式决定的确定值）；
    2. `model_kind == "relay"`    → 恒 False（中转站永不发 DeepSeek 专有 thinking 形状，
       即使 provider 名字以 deepseek 开头、或 base_url 恰好含 deepseek.com）；
    3. `model_kind` 为空（老数据）→ 回退 8e09bdf 的判据：provider 为 deepseek 系 **且**
       base_url 含 `deepseek.com`（或为空，沿用原逻辑）。

    ⚠️ 抽成单一函数：历史上 `_build_llm` 与 `build_agent_llm` 各写了一段等价但
       写法不一致的判据（其中一段还带无意义的 `"provider" in dir(config)`），
       两处来回改极易漏；现在统一走这里。
    """
    kind = (getattr(config, "model_kind", None) or "").strip().lower()
    is_ds_provider = (config.provider or "").startswith("deepseek")
    if kind == "official":
        return is_ds_provider
    if kind == "relay":
        return False
    base_l = (config.base_url or "").lower()
    return is_ds_provider and ("deepseek.com" in base_l or not base_l)


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
    thinking: Any = None,
    files: Optional[list] = None,
    as_attachment: bool = False,
) -> ChatOpenAI:
    """根据表配置动态构建 OpenAI 兼容客户端（支持深度思考开关）

    深度思考通过 `extra_body` 透传（DeepSeek 兼容参数）：
    - 开启：{"thinking": {"type": "enabled"}, "reasoning_effort": <配置值>}
    - 关闭：{"thinking": {"type": "disabled"}}
    - 跟随默认：不传，交给模型自己决定

    `thinking` 传 `_OMIT_THINKING` 表示**强制什么都不发**（不看配置），
    Agent 模式用它来避免发出 `disabled` 形状 —— 详见 `build_agent_llm`。
    """
    base_url = (config.base_url or "").strip() or PROVIDER_BASE_URLS.get(config.provider) or "https://api.deepseek.com/v1"

    extra_body: dict = {}
    resolved = None if thinking is _OMIT_THINKING else _resolve_thinking(config, thinking)
    #: 是否**官方** DeepSeek 域（认 `{"thinking":{"type":"enabled"}}` 这套专有形状）。
    #: 判据统一走 `_is_official_deepseek`：优先读 model_kind（official/relay），
    #: 老数据为空时回退 base_url 判据。
    is_deepseek = _is_official_deepseek(config)
    if resolved is True:
        if is_deepseek:
            extra_body["thinking"] = {"type": "enabled"}
        # 无论哪家，只要配了 reasoning_effort 就带上（OpenAI 标准参数，网关据此开深度思考）
        effort = (config.reasoning_effort or "").strip()
        if effort:
            extra_body["reasoning_effort"] = effort
    elif resolved is False:
        # 显式关闭：`thinking` 形状只发给认识的官方 deepseek，别家不塞脏参数
        if is_deepseek:
            extra_body["thinking"] = {"type": "disabled"}

    # 文件附件：**只发给本机 DS 网页桥**（provider=ds-free-nb）。
    # 桥收到 top-level `files` 后会把文件原样上传到 chat.deepseek.com，由 DS 网页自己解析
    #（比后端 file_parser 更准）。其它 provider（OpenAI/DeepSeek 官方等）不认识该字段，
    # 若也塞进去可能被拒，故**按 provider 收口**。
    # ⚠️ langchain 会把 extra_body 合并到请求 JSON 的**顶层**，桥的 extractFileAttachments 读的正是顶层 `files`。
    _is_bridge = (config.provider or "").strip().lower() == "ds-free-nb"
    if files and _is_bridge:
        extra_body["files"] = files
        logger.info(f"[db_config] 附加文件附件 {len(files)} 个 → ds-free-nb 桥")
    # 是否把**正文**投递为附件（用户开了「注入历史记忆」开关时；见 ChatTurn.inject_history）。
    # 桥据此把正文写成 .md 附件上传，输入框只留短指令，避免长历史灌框卡死。
    if as_attachment and _is_bridge:
        extra_body["asAttachment"] = True
        logger.info("[db_config] 本轮正文投递为附件（asAttachment=true）")

    # 缺 Key 时提前抛「人话」错误。
    # 否则 openai SDK 会抛英文的 "The api_key client option must be set either by
    # passing api_key to the client or by setting the OPENAI_API_KEY environment
    # variable"，既看不出是哪条配置的问题，也不知道该怎么修。
    api_key = (config.api_key or "").strip()
    if _is_placeholder_key(api_key):
        api_key = (settings.DEEPSEEK_API_KEY or "").strip()
    if _is_placeholder_key(api_key):
        raise RuntimeError(_no_credential_message(config))

    kwargs = dict(
        model=config.model,
        temperature=temperature,
        max_tokens=max_tokens,
        openai_api_key=api_key,
        openai_api_base=base_url,
    )
    if extra_body:
        kwargs["extra_body"] = extra_body
        # ⚠️ **绝不**打印 extra_body 的 value：`files` 里含整份文档的 base64，
        #    原样 log 会刷爆日志（用户 2026-10-12 报）。只打 key 摘要。
        logger.info(
            f"[db_config] thinking resolved={resolved}, extra_body keys={list(extra_body.keys())}"
            + (f" (+files×{len(extra_body['files'])})" if "files" in extra_body else "")
        )
    return ChatOpenAI(**kwargs)


async def stream_with_config(
    db: AsyncSession,
    messages: List[ChatMessage],
    provider: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 8000,
    thinking: Optional[bool] = None,
    model: Optional[str] = None,
    user_id: Optional[int] = None,
    files: Optional[list] = None,
    as_attachment: bool = False,
) -> AsyncIterator[str]:
    """流式输出：优先使用 sys_ai_config 表配置；表无配置时回退内置 dynamic_ai 路由

    model / provider 都为空时使用默认；model 优先于 provider。
    user_id 决定可见范围（系统模型 + 自己的自定义模型）。
    files：**原始文件附件** `[{name, mimeType, base64}]`，仅对 ds-free-nb 桥生效
           （桥把它们原样上传到 DS 网页，由网页解析）。
    as_attachment：正文是否投递为附件（仅 ds-free-nb），见 ChatTurn.inject_history。
    注意：这里**只输出正式回答（content）**，深度思考的 reasoning_content 会被丢弃，
    前端用「思考中」动画来占位即可。
    """
    config = await resolve_config(db, provider, model, user_id)
    if config:
        # ds-free 走网页端反代，不是 OpenAI 兼容接口，单独分支
        if config.provider == DS_FREE_PROVIDER:
            logger.info("[db_config] Using ds-free web client")
            async for kind, text in _stream_via_web_client(config, messages, include_reasoning=False):
                if kind == "answer":
                    yield text
            return

        logger.info(
            "[db_config] Using table config: config_id={} provider={} model={} has_key={}",
            config.config_id, config.provider, config.model, has_credentials(config),
        )
        llm = _build_llm(config, temperature, max_tokens, thinking, files=files, as_attachment=as_attachment)
        async for chunk in llm.astream(_to_lc_messages(messages)):
            # 只转发正式回答；reasoning_content 不输出
            if chunk.content:
                yield chunk.content
        return

    # 回退：内置注册的客户端（provider 可能为 None，走默认 provider）
    logger.info(f"[db_config] No table config for provider={provider} model={model}, fallback to dynamic_ai")
    async for chunk in dynamic_ai.chat_stream(
        messages, model="deepseek-flash", provider=provider, temperature=temperature
    ):
        yield chunk


async def _stream_via_web_client(config: SysAiConfig, messages: List[ChatMessage], include_reasoning: bool = False):
    """ds-free 已改由前端浏览器扩展实现，后端不再走 HTTP 反代。

    当前架构（v2）：
        ds-free = 浏览器扩展方案
          前端 utils/ds-proxy.ts → window.DSProxy（扩展注入）
            → 扩展 background 定位 chat.deepseek.com 标签页
            → 该页 DOM 自动化发送；MAIN world 劫持自身 SSE 流读回复
        因此 ds-free 的请求根本不该走到后端。

    历史上这里用 DeepSeekWebClient 做过纯 HTTP 反代（能跑通，但需要每 24 小时
    人工从浏览器导出 token/cookie，且依赖官方 wasm 解 PoW），已废弃。
    代码保留在 app/services/ai/deepseek_web_client.py 与 pow_wasm/ 备查。
    """
    raise RuntimeError(
        "ds-free 由前端浏览器扩展处理，请勿在后端调用。"
        "如果这条错误出现在前端的模型下拉框选 ds-free 时，说明前端还没接上 "
        "utils/ds-proxy.ts 里的 chatWithDS()。"
    )
    yield  # pragma: no cover  保持异步生成器语义


async def chat_with_config(
    db: AsyncSession,
    messages: List[ChatMessage],
    provider: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 8000,
    thinking: Optional[bool] = None,
    model: Optional[str] = None,
    user_id: Optional[int] = None,
) -> ChatResponse:
    """非流式输出：优先使用 sys_ai_config 表配置（model 优先于 provider）"""
    config = await resolve_config(db, provider, model, user_id)
    if config:
        if config.provider == "deepseek-free":
            logger.info("[db_config] Using ds-free web client (non-stream)")
            answer = ""
            async for kind, text in _stream_via_web_client(config, messages):
                if kind == "answer":
                    answer += text
            return ChatResponse(content=answer)

        logger.info(f"[db_config] Using table config: provider={config.provider}, model={config.model}")
        llm = _build_llm(config, temperature, max_tokens, thinking)
        response = await llm.ainvoke(_to_lc_messages(messages))
        return ChatResponse(content=response.content)

    response = await dynamic_ai.chat(
        messages, model="deepseek-flash", provider=provider, temperature=temperature
    )
    return response


# ============================================================
# Agent（Function Calling）专用
# ============================================================


def supports_tools(config: SysAiConfig) -> bool:
    """该配置能否用于 Agent 的**原生 Function Calling**

    ds-free 走浏览器扩展代发网页端请求，协议上挂不了 `tools` 参数 → 不能。
    官方 API（DeepSeek / 智谱 / 硅基流动）都是 OpenAI 兼容且支持工具调用 → 能。
    """
    return is_servable_by_backend(config)


async def resolve_agent_config(
    db: AsyncSession,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    user_id: Optional[int] = None,
) -> SysAiConfig:
    """解析 Agent 要用的模型配置；不可用时抛出**中文可行动**错误

    错误文案直接面向用户，因为它会通过 SSE 的 `Error: ` 契约显示在聊天区 ——
    「The api_key client option must be set」这种英文堆栈对用户毫无帮助。
    """
    config = await resolve_config(db, provider, model, user_id)
    if config is None:
        raise RuntimeError(
            "没有可用的 AI 模型配置，无法启动 Agent。\n"
            "请联系【管理员】进入后台「系统管理 → AI 模型配置」启用并配置一个官方模型；"
            "或到「个人中心 → 我的模型」添加你自己的模型。"
        )
    if not supports_tools(config):
        raise RuntimeError(
            f"Agent 模式需要官方 API 模型，当前选中的「{config.provider_name or config.provider}」"
            "是 DS 网页版（ds-free），它的请求由浏览器扩展代发、无法携带工具定义。"
            "请在模型下拉框里切换到 deepseek-flash / deepseek-v4-pro 等官方模型。"
        )
    if not has_credentials(config):
        raise RuntimeError(_no_credential_message(config))
    return config


async def build_agent_llm(
    db: AsyncSession,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 8000,
    user_id: Optional[int] = None,
    files: Optional[list] = None,
    as_attachment: bool = False,
):
    """构建 Agent 用的 ChatOpenAI（**不主动关闭深度思考**）

    ⚠️ 这里曾经强制 `thinking={"type":"disabled"}`，依据是「DeepSeek 的 thinking
    模式与 Function Calling 互斥」。该依据**已被实测推翻**：绑定工具 + 开启思考后，
    上游照常返回 tool_call 分片，工具调用完全正常（实测 10 个分片）。

    反过来「主动关闭」才是真正的坑：`disabled` 会在**上游**就把 reasoning_content
    掐掉（实测：传 disabled → 0 字；不传 → 66 字），于是思考卡片永远不可能出现。

    现在的规则（provider 无关）：

    | 配置意图 | provider | 发出的 extra_body |
    |---|---|---|
    | 显式开启 | deepseek 系 | `{"thinking":{"type":"enabled"}, ...}` |
    | 显式开启 | 其它 | 不传（别把 DeepSeek 专有参数塞给别家） |
    | 显式关闭 / auto | 任意 | 不传 → 跟随上游默认 |

    「显式关闭」之所以也走「不传」：`{"thinking":{"type":"disabled"}}` 是 DeepSeek
    专有形状，对别的 OpenAI 兼容接口是脏参数；而且 Agent 模式的产品目标就是
    「能思考就展示」，真按关闭处理等于该功能不可用。
    非 Agent 的普通对话链路（`stream_with_config`）仍然照常尊重 `thinking_mode`。

    Returns:
        (llm, config)
    """
    config = await resolve_agent_config(db, provider, model, user_id)

    # 「要思考」这件事：
    #   · 官方 DeepSeek（api.deepseek.com）：认 `{"thinking":{"type":"enabled"}}`，显式开启时透传。
    #   · 其它 OpenAI 兼容网关（含**把 provider 标成 deepseek、但 base_url 指向自建网关/本地 magpie**
    #     的情况——用户 2026-10-12 实测正是如此）：不认 DeepSeek 的 thinking 形状，但**认标准
    #     `reasoning_effort`**；实测本地 magpie 传 `reasoning_effort:high` 才回 reasoning_content
    #     （不传 → 0 字）。故这类网关在 `auto` 下也应带上 reasoning_effort，否则"深度思考"永不出现。
    #   · 显式关闭（thinking_mode=disabled）：官方域发 disabled；别家不塞脏参数（见 _build_llm）。
    resolved_intent = _resolve_thinking(config, None)
    #: 是否**官方** DeepSeek 域（决定能否用 DeepSeek 专有的 `thinking` 形状）。
    #: 判据统一走 `_is_official_deepseek`（优先 model_kind，老数据回退 base_url）。
    is_official_deepseek = _is_official_deepseek(config)
    #: 配了 reasoning_effort 的**非官方** OpenAI 兼容网关（magpie 等）——用它开思考
    has_effort = bool((config.reasoning_effort or "").strip())
    if resolved_intent is False:
        # 显式关闭：官方域发 disabled；别家什么都不发
        thinking_arg: Any = False if is_official_deepseek else _OMIT_THINKING
    elif is_official_deepseek:
        # 官方 DeepSeek：enabled → True；auto → 不传（跟随上游默认）
        thinking_arg = True if resolved_intent is True else _OMIT_THINKING
    else:
        # 非官方 OpenAI 兼容网关（含自建 magpie）：配了 reasoning_effort 就传 True
        # （`_build_llm` 只带 reasoning_effort、不带 thinking 形状），否则不传。
        thinking_arg = True if has_effort else _OMIT_THINKING

    llm = _build_llm(
        config, temperature=temperature, max_tokens=max_tokens, thinking=thinking_arg, files=files, as_attachment=as_attachment
    )
    logger.info(
        "[db_config] Agent 客户端: config_id={} provider={} model={} thinking={}"
        "（None=不传，跟随上游默认）",
        config.config_id,
        config.provider,
        config.model,
        None if thinking_arg is _OMIT_THINKING else thinking_arg,
    )
    return llm, config
