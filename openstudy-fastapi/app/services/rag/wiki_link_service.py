"""Wiki 页面内链的纯函数工具。

设计参考 WeKnora 的 `wiki_linkify.go`，但不复制它的代码与数据结构：

- 页面正文里使用 ``[[page:<page_id>|显示文字]]`` 表示一条可跳转的百科内链；
- 生成/更新页面时，先由 LLM 按主题页候选写出 ``[[主题页标题|原词]]``，
  再由本模块把它们归一化成稳定的 page id；
- 自动补链时按标题/别名做最长匹配，只给每个目标页插入第一条安全匹配；
- 跳过代码块、行内代码、Markdown 链接/图片、数学公式和已有的 wiki 链接；
- 单汉字标题不做自动补链，避免把「风沙」「核心」这类普通词误切成链接。

这里的函数不连数据库，便于单元测试；落库逻辑在 `wiki_service.py`。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


#: 通用 wiki 文本标记：[[目标]] 或 [[目标|显示文字]]
WIKI_TOKEN_RE = re.compile(r"\[\[([^\[\]|]+)(?:\|([^\[\]]+))?\]\]")
#: 后端归一化后的稳定页面链接：[[page:123|显示文字]]
PAGE_LINK_RE = re.compile(r"\[\[page:(\d+)(?:\|([^\[\]]+))?\]\]")


def normalize_title(value: Any) -> str:
    """页面标题归一化：去掉空白、书名号与解释性后缀。"""
    title = re.sub(r"[\s\u3000]+", "", str(value or "").strip())
    title = title.strip("《》\"'“”‘’（）()[]【】")
    for suffix in ("定义", "概念", "概述", "简介", "介绍", "说明"):
        if len(title) > len(suffix) + 1 and title.endswith(suffix):
            title = title[: -len(suffix)]
            break
    return title.lower()


def clean_text(value: Any, limit: int = 4000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _is_single_han(value: str) -> bool:
    return len(value) == 1 and "\u4e00" <= value <= "\u9fff"


def _is_ascii_word(char: str) -> bool:
    return bool(char) and char.isascii() and (char.isalnum() or char == "_")


def _has_word_boundary(text: str, start: int, end: int) -> bool:
    if start > 0 and _is_ascii_word(text[start - 1]):
        return False
    if end < len(text) and _is_ascii_word(text[end]):
        return False
    return True


def _merge_spans(spans: Sequence[Tuple[int, int]]) -> list[tuple[int, int]]:
    ordered = sorted((max(0, int(a)), max(0, int(b))) for a, b in spans if b > a)
    merged: list[tuple[int, int]] = []
    for start, end in ordered:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _forbidden_spans(text: str) -> list[tuple[int, int]]:
    """返回不能插入链接的区间：代码、已有链接、Markdown 链接/图片、公式。"""
    patterns = (
        r"(?ms)^[ \t]*```[^\n]*\n.*?^[ \t]*```[ \t]*$",
        r"(?ms)^[ \t]*~~~[^\n]*\n.*?^[ \t]*~~~[ \t]*$",
        r"`[^`\n]+`",
        r"\[\[[^\]]+\]\]",
        r"!\[[^\]]*\]\([^)\n]+\)",
        r"\[[^\]]*\]\([^)\n]+\)",
        r"\$\$[\s\S]*?\$\$",
        r"(?<!\$)\$[^$\n]+\$(?!\$)",
    )
    spans: list[tuple[int, int]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            spans.append((match.start(), match.end()))
    return _merge_spans(spans)


def _find_first_safe(text: str, needle: str, forbidden: Sequence[Tuple[int, int]]) -> int:
    if not needle:
        return -1
    needs_boundary = bool(
        (_is_ascii_word(needle[0]) if needle else False)
        or (_is_ascii_word(needle[-1]) if needle else False)
    )
    start = 0
    while start <= len(text) - len(needle):
        pos = text.find(needle, start)
        if pos < 0:
            return -1
        end = pos + len(needle)
        if any(pos < b and end > a for a, b in forbidden):
            start = pos + 1
            continue
        if needs_boundary and not _has_word_boundary(text, pos, end):
            start = pos + 1
            continue
        return pos
    return -1


def linkify_content(
    content: str,
    refs: Sequence[Mapping[str, Any]],
    self_page_id: Optional[int] = None,
) -> Tuple[str, int]:
    """给正文自动插入 ``[[page:id|原词]]`` 内链。

    refs 每项至少包含 ``pageId`` 和 ``matchText``；按 matchText 长度倒序匹配，
    长标题优先于它的子串；每个目标页只插入第一次安全出现，已有链接的目标跳过。
    返回 (新正文, 新增链接数)。
    """
    if not content or not refs:
        return content, 0

    already: set[int] = {
        int(match.group(1)) for match in PAGE_LINK_RE.finditer(content) if match.group(1).isdigit()
    }
    candidates: list[dict[str, Any]] = []
    seen_surfaces: set[str] = set()
    for item in refs:
        try:
            page_id = int(item.get("pageId"))
        except (TypeError, ValueError):
            continue
        match_text = str(item.get("matchText") or "").strip()
        if not match_text or page_id <= 0 or page_id == int(self_page_id or 0):
            continue
        if _is_single_han(match_text):
            continue
        key = f"{page_id}:{match_text}"
        if key in seen_surfaces:
            continue
        seen_surfaces.add(key)
        candidates.append({"pageId": page_id, "matchText": match_text})

    candidates.sort(key=lambda item: len(str(item["matchText"])), reverse=True)
    added = 0
    for item in candidates:
        page_id = int(item["pageId"])
        if page_id in already:
            continue
        match_text = str(item["matchText"])
        # 每次替换后重新计算禁区，避免新插入的 [[...]] 被后续词嵌套。
        pos = _find_first_safe(content, match_text, _forbidden_spans(content))
        if pos < 0:
            continue
        replacement = f"[[page:{page_id}|{match_text}]]"
        content = content[:pos] + replacement + content[pos + len(match_text) :]
        already.add(page_id)
        added += 1
    return content, added


def normalize_wiki_tokens(
    text: str,
    title_to_page: Mapping[str, Mapping[str, Any]],
    valid_page_ids: Iterable[int],
    self_page_id: Optional[int] = None,
) -> str:
    """把 LLM 写出的 ``[[标题|原词]]`` 统一成 ``[[page:id|原词]]``。

    目标页不存在、目标页是自己、或标题不在候选里时，只保留显示文字，不留下
    无效的方括号。
    """
    valid = {int(x) for x in valid_page_ids}
    self_id = int(self_page_id or 0)

    def replace(match: re.Match[str]) -> str:
        target = str(match.group(1) or "").strip()
        label = str(match.group(2) or target).strip() or target
        page_id = 0
        if target.lower().startswith("page:"):
            tail = target.split(":", 1)[1].strip()
            if tail.isdigit():
                page_id = int(tail)
        else:
            page = title_to_page.get(normalize_title(target))
            if page:
                try:
                    page_id = int(page.get("pageId"))
                except (TypeError, ValueError):
                    page_id = 0
        if page_id <= 0 or page_id not in valid or page_id == self_id:
            return label
        return f"[[page:{page_id}|{label}]]"

    return WIKI_TOKEN_RE.sub(replace, text or "")


def strip_wiki_tokens(text: str) -> str:
    """去掉 wiki 标记，只留显示文字；用于 RAG 索引、复制和长度统计。"""
    if not text:
        return ""

    def replace(match: re.Match[str]) -> str:
        label = match.group(2) or match.group(1) or ""
        return str(label).strip()

    return WIKI_TOKEN_RE.sub(replace, text)


def extract_wiki_links(text: str, section_index: int = -1) -> list[dict[str, Any]]:
    """解析文本里的稳定 page 链接，返回页面详情/反链需要的结构。"""
    items: list[dict[str, Any]] = []
    if not text:
        return items
    for match in PAGE_LINK_RE.finditer(text):
        try:
            page_id = int(match.group(1))
        except (TypeError, ValueError):
            continue
        anchor = str(match.group(2) or "").strip()
        items.append(
            {
                "pageId": page_id,
                "anchorText": anchor,
                "sectionIndex": int(section_index),
                "startOffset": int(match.start()),
                "endOffset": int(match.end()),
            }
        )
    return items


def page_text_blocks(summary: str, sections: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """按「摘要 = -1，小节 = 0..n」返回页面文本块。"""
    blocks: list[dict[str, Any]] = [{"sectionIndex": -1, "text": str(summary or "")}]
    for index, section in enumerate(sections or []):
        if isinstance(section, dict):
            blocks.append(
                {
                    "sectionIndex": int(index),
                    "text": str(section.get("body") or ""),
                }
            )
    return blocks


__all__ = [
    "WIKI_TOKEN_RE",
    "PAGE_LINK_RE",
    "normalize_title",
    "clean_text",
    "linkify_content",
    "normalize_wiki_tokens",
    "strip_wiki_tokens",
    "extract_wiki_links",
    "page_text_blocks",
]
