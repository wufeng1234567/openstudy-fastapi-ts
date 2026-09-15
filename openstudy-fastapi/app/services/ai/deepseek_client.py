"""
DeepSeek 客户端（使用 LangChain）
"""

from typing import List, AsyncIterator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.services.ai.base_client import BaseAiClient, ChatMessage, ChatResponse, TextBlock, ImageBlock
from app.config import settings


class DeepSeekClient(BaseAiClient):
    """DeepSeek 客户端"""

    def __init__(self, api_key: str = None):
        self._api_key = api_key or settings.DEEPSEEK_API_KEY

    @property
    def provider(self) -> str:
        return "deepseek"

    @property
    def supported_models(self) -> List[str]:
        return ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"]

    def _get_llm(self, model: str, temperature: float, max_tokens: int) -> ChatOpenAI:
        """获取 LangChain LLM 实例"""
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            openai_api_key=self._api_key,
            openai_api_base="https://api.deepseek.com",
        )

    def _convert_messages(self, messages: List[ChatMessage]) -> list:
        """转换消息格式（支持文本和图片混合内容）"""
        lc_messages = []
        for msg in messages:
            if msg.role == "system":
                lc_messages.append(SystemMessage(content=msg.content if isinstance(msg.content, str) else "\n".join(b.text for b in msg.content if isinstance(b, TextBlock))))
            elif msg.role == "user":
                # 支持多模态内容（文本+图片）
                if isinstance(msg.content, list):
                    lc_messages.append(HumanMessage(content=msg.content))
                else:
                    lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                lc_messages.append(AIMessage(content=msg.content if isinstance(msg.content, str) else ""))
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
            "model": model,
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
