"""手写文字图片 OCR 校对（仅用户直接上传的图片资料）。

为什么要单独一层：
- 普通文档里的插图不一定是文字，不能让模型把每一张图都“OCR”；
- 用户直接上传的图片才可能是手写笔记，需要识别 + 纠正错别字；
- 这里复用系统现有视觉模型（默认 deepseek-flash，多模态），不另建模型配置。

返回空字符串表示“不是手写文字图片”或视觉模型不可用；调用方仍可把图片作为
image-only 资料保存，不会因为 OCR 失败丢掉原图。
"""

from __future__ import annotations

import base64
import mimetypes
from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

_PROMPT = """你是一名手写文字 OCR 校对器。只处理图片中的手写文字：
1. 逐行完整识别手写内容，不要省略、总结或截断；
2. 纠正明显的错别字、漏字、OCR 断行错误，保持原意和段落顺序；
3. 保留公式、符号、数字和换行；
4. 不要输出解释、标题、Markdown 代码围栏或“识别结果：”之类前缀。
如果图片不是手写文字（例如纯照片、印刷文字、表格截图、图表、二维码、海报、装饰图），只输出：
[[NO_HANDWRITTEN_TEXT]]
"""


def _image_data_url(filename: str, raw: bytes) -> str:
    mime = mimetypes.guess_type(filename or "")[0] or "image/png"
    if not mime.startswith("image/"):
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


async def recognize_handwriting(
    db: AsyncSession, user_id: int, filename: str, raw: bytes
) -> str:
    """调用多模态模型识别手写文字并校对；失败返回空串，不阻断上传。"""
    if not raw:
        return ""
    try:
        from app.services.ai.base_client import ChatMessage, ImageBlock, TextBlock
        from app.services.ai.db_config import chat_with_config

        messages = [
            ChatMessage(
                role="user",
                content=[
                    TextBlock(type="text", text=_PROMPT),
                    ImageBlock(type="image_url", image_url={"url": _image_data_url(filename, raw)}),
                ],
            )
        ]
        response = await chat_with_config(
            db,
            messages,
            model="deepseek-flash",
            user_id=user_id,
            temperature=0.1,
            max_tokens=5000,
        )
        text = (response.content or "").strip()
        if not text or "[[NO_HANDWRITTEN_TEXT]]" in text:
            return ""
        # 兜底去掉模型偶尔加上的围栏/前缀，保持正文干净。
        text = text.replace("```markdown", "").replace("```", "").strip()
        if text.startswith("识别结果："):
            text = text[len("识别结果：") :].strip()
        return text
    except Exception as exc:  # noqa: BLE001 - OCR 失败不能阻断图片入库
        logger.warning(f"[handwriting] OCR failed for {filename}: {exc}")
        return ""
