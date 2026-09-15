"""
智谱 AI 客户端（使用 LangChain）
"""

from typing import List, AsyncIterator
from langchain_community.chat_models import ChatZhipuAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.services.ai.base_client import BaseAiClient, ChatMessage, ChatResponse
from app.config import settings


class ZhipuAiClient(BaseAiClient):
    """智谱 AI 客户端"""

    def __init__(self, api_key: str = None):
        self._api_key = api_key or settings.ZHIPU_API_KEY

    @property
    def provider(self) -> str:
        return "zhipu"

    @property
    def supported_models(self) -> List[str]:
        return ["glm-4", "deepseek-chat", "glm-4v", "glm-3", "embedding-3"]

    def _get_llm(self, model: str, temperature: float, max_tokens: int) -> ChatZhipuAI:
        """获取 LangChain LLM 实例"""
        return ChatZhipuAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=self._api_key,
        )

    def _convert_messages(self, messages: List[ChatMessage]) -> list:
        """转换消息格式"""
        lc_messages = []
        for msg in messages:
            if msg.role == "system":
                lc_messages.append(SystemMessage(content=msg.content))
            elif msg.role == "user":
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                lc_messages.append(AIMessage(content=msg.content))
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
            usage=getattr(response, "usage_metadata", None),
            raw=response,
        )

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> AsyncIterator[str]:
        llm = self._get_llm(model, temperature, max_tokens)
        lc_messages = self._convert_messages(messages)

        async for chunk in llm.astream(lc_messages):
            if chunk.content:
                yield chunk.content

    async def embeddings(
        self,
        texts: List[str],
        model: str = None,
    ) -> List[List[float]]:
        """使用智谱 embedding 模型"""
        from zhipuai import ZhipuAI

        client = ZhipuAI(api_key=self._api_key)
        response = client.embeddings.create(
            model=model or "embedding-3",
            input=texts,
        )
        return [item.embedding for item in response.data]


# 注册到 DynamicAI
from app.services.ai.dynamic_ai import dynamic_ai
dynamic_ai.register_client(ZhipuAiClient())
