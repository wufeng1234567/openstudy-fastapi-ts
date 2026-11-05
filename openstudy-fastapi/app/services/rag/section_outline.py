"""章节切片：给画廊 / 知识地图复用的「可导航」版本。

`document_health_service._section_slices` 会刻意过滤掉「第X章」这种一级章标题，
以免体检热力图多出只有标题的薄区块；但画廊定位和知识地图需要把章标题作为页面节点。
所以这里复用同一套标题识别，但保留所有标题。
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.document_health_service import _health_headings, _line_offsets


def content_sections(text: str) -> List[Dict[str, Any]]:
    raw = str(text or "")
    heads = _health_headings(raw)
    if not heads:
        return [{"index": 0, "title": "全文", "level": 1, "start": 0, "end": len(raw), "text": raw}]
    offsets = _line_offsets(raw)
    starts: List[tuple[int, Dict[str, Any]]] = []
    for head in heads:
        line_no = int(head.get("line") or 1)
        start = offsets[line_no - 1] if 0 <= line_no - 1 < len(offsets) else 0
        starts.append((start, head))
    sections: List[Dict[str, Any]] = []
    for idx, (start, head) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(raw)
        sections.append(
            {
                "index": idx,
                "title": str(head.get("title") or "未命名章节"),
                "level": int(head.get("level") or 1),
                "start": start,
                "end": max(start, end),
                "text": raw[start:end],
            }
        )
    return sections


__all__ = ["content_sections"]
