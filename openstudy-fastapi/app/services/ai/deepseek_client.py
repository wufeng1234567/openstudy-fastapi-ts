"""
DeepSeek 客户端（使用 LangChain）
"""

from typing import List, AsyncIterator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.services.ai.base_client import (
    BaseAiClient,
    ChatMessage,
    ChatResponse,
    ImageBlock,
    TextBlock,
    to_lc_content,
    to_lc_text,
)
from app.config import settings


class DeepSeekClient(BaseAiClient):
    """DeepSeek 客户端"""

    # 官方 API 模型名映射。
    #
    # ⚠️ 官方当前只提供两个模型：**`deepseek-flash`**（DeepSeek-V4.1-Flash）与 `deepseek-v4-pro`。
    #    新配置一律用 `deepseek-flash`。
    #    旧名 `deepseek-v4-flash` / `deepseek-v4-flash-vision-exp` 仍可调用，
    #    但**对应模型已下线** —— 请求由 DeepSeek-V4.1-Flash 提供服务、按 Flash 价格计费。
    #    `deepseek-chat` / `deepseek-coder` / `deepseek-reasoner` 也不再作为独立模型。
    #
    # 这里做别名映射，保证前端 / 数据库里遗留的旧模型名仍然可用。
    MODEL_ALIASES = {
        # 已下线模型的遗留名 —— 统一收敛到官方名，别让废弃名继续发到上游
        "deepseek-v4-flash": "deepseek-flash",
        "deepseek-chat": "deepseek-flash",
        "deepseek-coder": "deepseek-flash",
        "deepseek-reasoner": "deepseek-flash",
    }

    def __init__(self, api_key: str = None):
        self._api_key = api_key or settings.DEEPSEEK_API_KEY

    @property
    def provider(self) -> str:
        return "deepseek"

    @property
    def supported_models(self) -> List[str]:
        # ⚠️ 顺序有讲究：**官方名排最前**，后面是**兼容用的遗留别名**。
        #
        # `base_client.supports_model()` 用的是 `model.startswith(m)`，
        # 所以 `deepseek-flash` 必须出现在这个列表里，否则
        # `dynamic_ai.get_client_for_model("deepseek-flash")` 会匹配不到任何 provider，
        # 只能退化到「用默认 provider」的兜底分支（db_config 的回落路径正好传的就是
        # `deepseek-flash`）。新增官方名时记得同步这里。
        return [
            # ---- 官方名 ----
            "deepseek-flash",
            "deepseek-v4-pro",
            # ---- 以下均为已下线模型的遗留名，仅为让库里的旧配置仍能解析 ----
            "deepseek-v4-flash",
            "deepseek-chat",
            "deepseek-coder",
            "deepseek-reasoner",
        ]

    def _resolve_model(self, model: str) -> str:
        """把（可能已下线的）模型名解析为当前可用的官方模型 ID"""
        return self.MODEL_ALIASES.get(model, model)

    def _get_llm(self, model: str, temperature: float, max_tokens: int) -> ChatOpenAI:
        """获取 LangChain LLM 实例

        ⚠️ 这里是**内置静态客户端**（不读表配置），因此**不带** thinking /
        `reasoning_effort` 等高级参数。真正生效的构建入口是
        `db_config._build_llm`（按 `sys_ai_config` 的 thinking_mode /
        reasoning_effort / context_length 装配）—— 走 `dynamic_ai` 兜底时才用这里。
        """
        return ChatOpenAI(
            model=self._resolve_model(model),
            temperature=temperature,
            max_tokens=max_tokens,
            openai_api_key=self._api_key,
            openai_api_base="https://api.deepseek.com",
        )

    def _convert_messages(self, messages: List[ChatMessage]) -> list:
        """转换消息格式（支持文本和图片混合内容）

        ⚠️ content 为多模态块列表时必须 `to_lc_content()` 转 dict：
        TextBlock / ImageBlock 是 pydantic 模型，LangChain 只接受
        `list[str | dict]`，直接塞会抛 validation errors（发图即失败）。
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

    async def chat(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> ChatResponse:
        llm = self._get_llm(model, temperature, max_tokens)
        lc_messages = self._convert_messages(messages)

        response = await llm.ainvoke(lc_messages)

        return ChatResponse(
            content=response.content,
            usage=response.response_metadata.get("token_usage"),
            raw=response,
        )

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        include_reasoning: bool = False,
        **kwargs,
    ) -> AsyncIterator:
        if include_reasoning:
            async for chunk in self._chat_stream_with_reasoning(messages, model):
                yield chunk
            return

        llm = self._get_llm(model, temperature, max_tokens)
        lc_messages = self._convert_messages(messages)

        async for chunk in llm.astream(lc_messages):
            if chunk.content:
                yield chunk.content

    async def _chat_stream_with_reasoning(
        self,
        messages: List[ChatMessage],
        model: str,
    ) -> AsyncIterator:
        """直连 DeepSeek API 流式解析，将思考过程(reasoning_content)与正式回答(content)分开输出

        每个产出为 (kind, text) 元组，kind 为 "reasoning" 或 "answer"
        """
        import httpx
        import json

        system_parts = []
        user_parts = []
        user_images = []  # 收集用户消息中的图片

        for m in messages:
            if m.role == "system":
                if isinstance(m.content, str):
                    system_parts.append(m.content)
                else:
                    system_parts.append("\n".join(b.text for b in m.content if isinstance(b, TextBlock)))
            elif m.role == "user":
                if isinstance(m.content, str):
                    user_parts.append(m.content)
                else:
                    # 多模态内容：分离文本和图片
                    for block in m.content:
                        if isinstance(block, TextBlock):
                            user_parts.append(block.text)
                        elif isinstance(block, ImageBlock):
                            user_images.append(block.image_url)

        # 构建用户消息内容（支持图片）
        if user_images:
            # 有图片时使用 content 数组格式
            user_content = []
            if user_parts:
                user_content.append({"type": "text", "text": "\n".join(user_parts)})
            for img in user_images:
                user_content.append({"type": "image_url", "image_url": img})
        else:
            # 无图片时使用纯文本格式
            user_content = "\n".join(user_parts)

        payload = {
            "model": self._resolve_model(model),
            "stream": True,
            "messages": [
                {"role": "system", "content": "\n".join(system_parts)},
                {"role": "user", "content": user_content},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        timeout = httpx.Timeout(connect=30.0, read=300.0, write=60.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                "https://api.deepseek.com/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: "):]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    reasoning = delta.get("reasoning_content")
                    if reasoning:
                        yield ("reasoning", reasoning)
                    content = delta.get("content")
                    if content:
                        yield ("answer", content)

    async def embeddings(
        self,
        texts: List[str],
        model: str = None,
    ) -> List[List[float]]:
        from langchain_openai import OpenAIEmbeddings

        embeddings_model = OpenAIEmbeddings(
            model=model or "deepseek-embedding",
            openai_api_key=self._api_key,
            openai_api_base="https://api.deepseek.com",
        )
        return await embeddings_model.aembed_documents(texts)


# 注册到 DynamicAI
from app.services.ai.dynamic_ai import dynamic_ai
# 总是注册，API Key 可以后续通过配置更新
dynamic_ai.register_client(DeepSeekClient())
