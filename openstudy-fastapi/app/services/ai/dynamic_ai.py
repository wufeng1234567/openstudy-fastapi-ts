"""
DynamicAI 动态路由器
根据模型名称自动选择对应的客户端，不写死代码
"""

from typing import List, Optional, AsyncIterator, Dict
from app.services.ai.base_client import BaseAiClient, ChatMessage, ChatResponse
from loguru import logger


class DynamicAiRouter:
    """
    DynamicAI 动态路由器

    根据传入的模型名称自动选择对应的客户端
    不写死代码，只负责路由和验证
    """

    def __init__(self):
        self._clients: Dict[str, BaseAiClient] = {}
        self._default_provider: Optional[str] = None

    def register_client(self, client: BaseAiClient) -> None:
        """注册 AI 客户端"""
        self._clients[client.provider] = client
        logger.info(f"Registered AI client: {client.provider} with models: {client.supported_models}")

    def set_default_provider(self, provider: str) -> None:
        """设置默认提供商"""
        if provider not in self._clients:
            raise ValueError(f"Provider '{provider}' not registered")
        self._default_provider = provider

    def get_client_for_model(self, model: str) -> BaseAiClient:
        """
        根据模型名称获取对应的客户端

        模型名称格式：
        - deepseek-chat -> DeepSeek
        - deepseek-chat -> 智谱
        - Qwen/Qwen2.5-7B-Instruct -> 硅基流动
        """
        for provider, client in self._clients.items():
            if client.supports_model(model):
                logger.debug(f"Model '{model}' matched to provider '{provider}'")
                return client

        if self._default_provider and self._default_provider in self._clients:
            logger.warning(f"No client found for model '{model}', using default: {self._default_provider}")
            return self._clients[self._default_provider]

        raise ValueError(f"No client found for model '{model}' and no default provider set")

    def get_client(self, provider: str) -> BaseAiClient:
        """根据提供商名称获取客户端"""
        if provider not in self._clients:
            raise ValueError(f"Provider '{provider}' not registered")
        return self._clients[provider]

    async def chat(
        self,
        messages: List[ChatMessage],
        model: str,
        provider: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> ChatResponse:
        """聊天"""
        if provider:
            client = self.get_client(provider)
        else:
            client = self.get_client_for_model(model)

        logger.info(f"Chat request: provider={client.provider}, model={model}")
        return await client.chat(messages, model, temperature, max_tokens, **kwargs)

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        model: str,
        provider: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        include_reasoning: bool = False,
        **kwargs,
    ) -> AsyncIterator:
        """流式聊天"""
        if provider:
            client = self.get_client(provider)
        else:
            client = self.get_client_for_model(model)

        logger.info(f"Stream chat request: provider={client.provider}, model={model}, include_reasoning={include_reasoning}")
        async for chunk in client.chat_stream(messages, model, temperature, max_tokens, include_reasoning=include_reasoning, **kwargs):
            yield chunk

    async def embeddings(
        self,
        texts: List[str],
        model: str = None,
        provider: str = None,
    ) -> List[List[float]]:
        """文本向量化"""
        if provider:
            client = self.get_client(provider)
        elif model:
            client = self.get_client_for_model(model)
        else:
            client = self.get_client("zhipu")
            model = "embedding-3"

        logger.info(f"Embeddings request: provider={client.provider}, model={model}")
        return await client.embeddings(texts, model)

    def list_providers(self) -> List[str]:
        """列出所有已注册的提供商"""
        return list(self._clients.keys())

    def list_models(self) -> Dict[str, List[str]]:
        """列出所有提供商支持的模型"""
        return {
            provider: client.supported_models
            for provider, client in self._clients.items()
        }


# 全局实例
dynamic_ai = DynamicAiRouter()
