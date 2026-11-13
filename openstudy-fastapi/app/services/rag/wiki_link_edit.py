"""Wiki 正文内链的**手工增删**（从 `wiki_service.py` 抽出）。

这些函数只做「正文里怎么找、怎么改」：

  · `page_link_pattern` —— 某个目标页的内链标记（`[[page:id|锚文本]]`）
  · `blocks_in_section` —— 挑出属于指定小节的正文块（-1 = 摘要）
  · `find_anchor_block` —— 找到**含锚文本**的那一块
  · `find_link_match` —— 找到要移除的那条内链（所在块 + 匹配）
  · `insert_link_marker` —— 在锚文本位置插入内链标记
  · `replace_link_with_text` —— 把内链标记还原成普通文字
  · `apply_block_text` —— 把改好的正文写回页面

⚠ 依赖方向单向：`wiki_service.py` → 本模块 → `wiki_content_helpers`（取锚点定位）；
   **不反向依赖** `wiki_service.py`，因此不会形成循环依赖。

⚠ **落库 / 检索 / 页面渲染流程一个字节都没动** —— 这里只把「正文里怎么找、怎么改」
   挪到了可独立读、可独立测的地方；`page` 的写回顺序、版本号递增、提交时机原样保留。

⚠ 「加链接」与「删链接」两个入口原本**各写一遍**同样的「按小节过滤 → 找到块 →
   改写正文 → 写回页面」—— 现在收敛到同一份实现，两边口径不会再漂。
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from app.services.rag.wiki_content_helpers import _find_anchor_position


def page_link_pattern(target_page_id: int) -> "re.Pattern[str]":
    """某个目标页的正文内链标记（`[[page:id|锚文本]]`）"""
    return re.compile(rf"\[\[page:{int(target_page_id)}(?:\|([^\[\]]+))?\]\]")


def blocks_in_section(blocks: List[dict], section_index: Optional[int]) -> List[dict]:
    """挑出属于指定小节的正文块（`section_index=None` → 全部；-1 = 摘要）"""
    if section_index is None:
        return list(blocks)
    return [b for b in blocks if int(b["sectionIndex"]) == int(section_index)]


def find_anchor_block(
    blocks: List[dict], section_index: Optional[int], anchor: str
) -> Optional[dict]:
    """找到**含锚文本**的那一块（先按小节过滤，再逐块找锚文本）"""
    for block in blocks_in_section(blocks, section_index):
        if _find_anchor_position(str(block["text"]), anchor) >= 0:
            return block
    return None


def find_link_match(
    blocks: List[dict],
    section_index: Optional[int],
    pattern: "re.Pattern[str]",
    desired_anchor: str,
) -> Tuple[Optional[dict], Optional["re.Match[str]"]]:
    """找到要移除的那条内链 → （所在块, 匹配）

    ⚠️ `desired_anchor` 非空时**只认锚文本完全一致**的那一条；
       为空时取该小节里的第一条。
    """
    for block in blocks_in_section(blocks, section_index):
        for match in pattern.finditer(str(block["text"])):
            label = str(match.group(1) or "").strip()
            if desired_anchor and label != desired_anchor:
                continue
            return block, match
    return None, None


def insert_link_marker(text: str, pos: int, target_page_id: int, anchor: str) -> str:
    """在锚文本位置插入内链标记"""
    replacement = f"[[page:{int(target_page_id)}|{anchor}]]"
    return text[:pos] + replacement + text[pos + len(anchor) :]


def replace_link_with_text(text: str, match: "re.Match[str]", label: str) -> str:
    """把一条内链标记还原成普通文字（正文其余部分原样保留）"""
    return text[: match.start()] + (label or "链接") + text[match.end() :]


def apply_block_text(page: Any, block: dict, new_text: str) -> None:
    """把改好的正文写回页面（-1 → 摘要；否则 → 对应小节）

    ⚠️ 小节不存在时抛错，**不做部分写入** —— 宁可让调用方整轮失败，
       也不能把改了一半的正文落库。
    """
    if int(block["sectionIndex"]) == -1:
        page.summary = new_text
        return
    sections = [dict(item) if isinstance(item, dict) else item for item in (page.sections or [])]
    idx = int(block["sectionIndex"])
    if idx >= len(sections) or not isinstance(sections[idx], dict):
        raise ValueError("小节不存在，请刷新后重试")
    sections[idx]["body"] = new_text
    page.sections = sections
