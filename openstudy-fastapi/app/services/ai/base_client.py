"""
AI 客户端基类
"""

from abc import ABC, abstractmethod
from typing import List, Optional, AsyncIterator, Any, Union
from pydantic import BaseModel


class ImageBlock(BaseModel):
    """图片内容块"""
    type: str = "image_url"
    image_url: dict  # {"url": "data:image/jpeg;base64,..."} 或 {"url": "https://..."}


class TextBlock(BaseModel):
    """文本内容块"""
    type: str = "text"
    text: str


class ChatMessage(BaseModel):
    """聊天消息"""
    role: str
    content: Union[str, List[Union[TextBlock, ImageBlock]]]


class ChatResponse(BaseModel):
    """聊天响应"""
    content: str
    usage: Optional[dict] = None
    raw: Optional[Any] = None


class BaseAiClient(ABC):
    """AI 客户端基类"""

    @property
    @abstractmethod
    def provider(self) -> str:
        """提供商名称"""
        pass

    @property
    @abstractmethod
    def supported_models(self) -> List[str]:
        """支持的模型列表"""
        pass

    def supports_model(self, model: str) -> bool:
        """检查是否支持指定模型"""
        return any(model.startswith(m) for m in self.supported_models)

    @abstractmethod
    async def chat(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> ChatResponse:
        """聊天"""
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式聊天"""
        pass

    @abstractmethod
    async def embeddings(
        self,
        texts: List[str],
        model: str = None,
    ) -> List[List[float]]:
        """文本向量化"""
        pass
