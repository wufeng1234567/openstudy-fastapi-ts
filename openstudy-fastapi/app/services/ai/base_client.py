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


def to_lc_text(content: Union[str, List[Any], None]) -> str:
    """把 content 压成纯文本 —— 给 system / assistant 消息用

    LangChain 的 SystemMessage / AIMessage 只接受字符串；如果内容是
    `[TextBlock, ImageBlock]` 这样的多模态块列表，就只取其中的文字部分
    （图片没法塞进 system / assistant，忽略即可）。
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, TextBlock):
                parts.append(block.text)
            elif isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
        return "\n".join(p for p in parts if p)
    return str(content)


def to_lc_content(content: Union[str, List[Any]]) -> Union[str, List[Any]]:
    """把 `ChatMessage.content` 转成 LangChain 能接受的形式

    ⚠️ 必踩的坑：LangChain 的 `HumanMessage.content` 类型是
    `Union[str, list[str | dict]]`，**不接受 pydantic 模型实例**。
    而 TextBlock / ImageBlock 都是 BaseModel，**直接塞进去**会在构造
    HumanMessage 时被 pydantic 打回，整轮请求直接失败：

        Input should be a valid string
        [type=string_type,
         input_value=[TextBlock(type='text', text='输出单词给我'),
                      ImageBlock(type='image_url', image_url={...})]]

    所以送进 LangChain 之前必须统一 `model_dump()` 成 dict。
    症状：**纯文字对话一切正常，一发图片就报 validation errors**。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        blocks: List[Any] = []
        for block in content:
            if isinstance(block, (str, dict)):
                blocks.append(block)
            elif isinstance(block, BaseModel):
                # exclude_none 让块更干净，也避免个别上游对多余 null 字段挑剔
                dumped = block.model_dump(exclude_none=True)
                if "type" not in dumped:
                    # 上游要求每个块都带 type；缺了就按文本块兜底
                    dumped = {"type": "text", "text": str(block)}
                blocks.append(dumped)
            else:
                # 未知类型兜底成文本块，别为了一个附件把整轮请求搞挂
                blocks.append({"type": "text", "text": str(block)})
        return blocks
    if isinstance(content, BaseModel):
        return content.model_dump(exclude_none=True)
    return str(content)


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
