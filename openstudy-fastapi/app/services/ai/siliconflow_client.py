"""
硅基流动客户端（使用 LangChain）
"""

from typing import List, AsyncIterator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.services.ai.base_client import BaseAiClient, ChatMessage, ChatResponse
from app.config import settings


class SiliconFlowClient(BaseAiClient):
    """硅基流动客户端"""

    def __init__(self, api_key: str = None):
        self._api_key = api_key or settings.SILICONFLOW_API_KEY

    @property
    def provider(self) -> str:
        return "siliconflow"

    @property
    def supported_models(self) -> List[str]:
        return [
            "Qwen/Qwen2.5-7B-Instruct",
            "Qwen/Qwen2.5-14B-Instruct",
            "Qwen/Qwen2.5-32B-Instruct",
            "Qwen/Qwen2.5-72B-Instruct",
            "deepseek-ai/DeepSeek-V2-Chat",
            "THUDM/glm-4-9b-chat",
        ]

    def _get_llm(self, model: str, temperature: float, max_tokens: int) -> ChatOpenAI:
        """获取 LangChain LLM 实例"""
        return ChatOpenAI(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            openai_api_key=self._api_key,
            openai_api_base="https://api.siliconflow.cn/v1",
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
            usage=response.response_metadata.get("token_usage"),
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
        from langchain_openai import OpenAIEmbeddings

        embeddings_model = OpenAIEmbeddings(
            model=model or "BAAI/bge-large-zh-v1.5",
            openai_api_key=self._api_key,
            openai_api_base="https://api.siliconflow.cn/v1",
        )
        return await embeddings_model.aembed_documents(texts)


# 注册到 DynamicAI
from app.services.ai.dynamic_ai import dynamic_ai
if settings.SILICONFLOW_API_KEY:
    dynamic_ai.register_client(SiliconFlowClient())
