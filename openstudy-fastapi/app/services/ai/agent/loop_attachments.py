"""Agent 循环的**附件处理**（从 `loop.py` 抽出）。

职责：把用户上传的文档附件变成「带【图N】标记的正文」：

  · **`_attachment_field`** —— 读附件字段（兼容 pydantic 模型与 dict）
  · **`_collect_attachments`** —— 遍历文档附件 → (拼接正文, 文档插图, 告警, 结构化附件列表)
  · **`_attachment_plain_text`** —— 取「干净的纯文本」（供写入知识库用）
  · **`_IMAGE_EXT`** —— 允许落盘的图片类型 → 扩展名

⚠️ 依赖方向单向：`loop.py` → 本模块 → `loop_support`（只取类型与标签常量）。
   本模块**不反向依赖** `loop.py`，因此不会形成循环依赖。

⚠️ `chat_engine` / `file_parser` 的 import 刻意留在**函数体内**（沿用原实现）——
   那两个模块体量不小，放模块级会拖慢导入、也容易和 `ai` 包的其它模块撞出循环依赖。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.services.ai.agent.loop_support import (
    TAG_DOCUMENT,
    AgentRequest,
    _safe_attr,
    _wrap_tag,
)
from app.services.file_parser import build_marked_document


#: 允许落盘的图片类型 → 扩展名
_IMAGE_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/webp": ".webp",
}


def _attachment_field(item: Any, key: str, default: str = "") -> str:
    """读附件字段（兼容 pydantic 模型与 dict）—— 同 chat_engine 的口径"""
    value = getattr(item, key, None)
    if value is None and isinstance(item, dict):
        value = item.get(key)
    return value if isinstance(value, str) else (default if value is None else str(value))


def _collect_attachments(
    req: AgentRequest,
) -> Tuple[str, List[str], List[str], List[Dict[str, str]]]:
    """遍历文档附件 → (拼接正文, 文档插图 data URL, 告警, 结构化附件列表)

    正文用 `<document name="...">` 包裹。这层标签同时干两件事：
      ① 告诉模型「这是文件内容，不是用户说的话」；
      ② 多个附件时天然分段，模型不会把两个文档的内容串在一起。

    第 4 个返回值 `structured`（`[{"name": ..., "text": ...}]`）是给
    `knowledge_ingest` 工具的 `from_attachment` 用的 —— 它需要**附件名 + 该附件的
    纯文本**（未包 `<document>` 标签的原始正文）来把内容写进知识库。
    这里**顺带**产出、不重复解析（解析是同步重活，老 .doc 还会借 Word COM）。
    """
    from app.services.ai.chat_engine import data_url_to_bytes
    from app.services.file_parser import parse_file

    offset = len(req.images or [])
    sections: List[str] = []
    doc_images: List[str] = []
    warnings: List[str] = []
    structured: List[Dict[str, str]] = []

    for item in req.files or []:
        name = (_attachment_field(item, "name") or "file").strip() or "file"
        try:
            content, _mime = data_url_to_bytes(_attachment_field(item, "base64"))
        except Exception as e:  # noqa: BLE001
            warnings.append(f"附件 {name} 解码失败：{e}")
            continue
        try:
            parsed = parse_file(name, content)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"附件 {name} 解析失败：{e}")
            continue

        marked, images = build_marked_document(parsed, offset + len(doc_images))
        error = parsed.get("error")
        attrs = f'name="{_safe_attr(name)}"'

        if marked:
            sections.append(_wrap_tag(TAG_DOCUMENT, marked, attrs))
        elif images:
            sections.append(
                _wrap_tag(
                    TAG_DOCUMENT,
                    "(this file contains only images; see the markers listed below)",
                    attrs,
                )
            )
        else:
            warnings.append(f"附件 {name}：{error or '没有提取到可用的文字或图片'}")

        if images:
            doc_images.extend(images)

        # 供 knowledge_ingest.from_attachment 使用：附件名 + 去标记的纯文本。
        # 只收「有正文」的附件（纯图片附件没有可入库的文本，跳过即可）。
        plain = _attachment_plain_text(parsed)
        if plain.strip():
            structured.append({"name": name, "text": plain})

    return "\n\n".join(sections), doc_images, warnings, structured


def _attachment_plain_text(parsed: Any) -> str:
    """从 `parse_file` 的结果里取「干净的纯文本」（供写入知识库用）

    `parse_file` 的正文口径见其 docstring：字段名是 **`textContent`**
    （不是 `text` / `content`），`marked` 版本才带【图N】标记与 `$latex$` 等标记。
    这里要的是**原始纯文本**（不含标记），所以直接取 `textContent`。
    取不到就回空串（调用方会跳过该附件）。
    """
    if not isinstance(parsed, dict):
        return ""
    value = parsed.get("textContent")
    if isinstance(value, str) and value.strip():
        return value
    return ""
