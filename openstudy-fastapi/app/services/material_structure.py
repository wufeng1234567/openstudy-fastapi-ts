"""结构化整理：编号、题目/答案、表格行、章节顺序的确定性布局计划。

这里只生成“把哪些块换到什么位置”的布局操作，**不改写任何正文**：

- 编号段落：按编号升序重排（01/02/04/06/08/09）
- 题目：按题号升序重排，答案按“第N题答案”归属跟随题目（03）
- 表格：表格行按首列编号升序排序（04）
- 章节：第三章被附录/参考文献隔开时，移回章节区（07）

输出格式与 `workspace_service._change()` 解耦：这里给业务字段，服务层负责拼
before/after 文案。真正应用由 `apply_plan` 的 layout 槽位替换完成，代码块、
公式块、表格内容、答案正文都不会被改写。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.services.material_organizer import (
    _CHAPTER_RE,
    _SECTION_BOUNDARY_RE,
    build_blocks,
)

_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|(?:\s*:?-{3,}\s*\|)+\s*$")

_CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CN_UNITS = {"十": 10, "百": 100}


def _cn_to_int(value: str) -> Optional[int]:
    """把“一 / 十二 / 二十三 / 105”解析成整数；失败返回 None。"""
    text = (value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    current = 0
    for ch in text:
        if ch in _CN_DIGITS:
            current = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            unit = _CN_UNITS[ch]
            if unit == 10:
                total += (current or 1) * 10
            else:
                total += (current or 1) * 100
            current = 0
        else:
            return None
    return total + current


def _short(value: str, limit: int = 56) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _chapter_sections(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """返回章节小节：标题块、起止偏移、章节号。

    紧邻的重复章节标题（07 的“第一章”出现了两次）不另起一节，交给
    duplicate_heading_suggestions() 作为“剔除重复标题”建议。
    """
    headings: List[Dict[str, Any]] = []
    for block in blocks:
        if block.get("kind") != "heading":
            continue
        text_value = block.get("text") or ""
        match = _CHAPTER_RE.match(text_value)
        if not match:
            continue
        # 目录行“第一章 智能体定义 ........ 3”不是正文章节，不能参与章节排序。
        if re.search(r"\.{2,}", text_value):
            continue
        number = _cn_to_int(match.group(1))
        if number is None:
            continue
        if headings:
            prev = headings[-1]
            if (
                re.sub(r"\s+", "", prev["text"]) == re.sub(r"\s+", "", block["text"])
                and int(block["start"]) - int(prev["end"]) <= 2
            ):
                continue
        headings.append({**block, "number": number})

    boundaries = [
        int(block["start"])
        for block in blocks
        if block.get("kind") == "heading"
        and _SECTION_BOUNDARY_RE.match(block.get("text") or "")
    ]
    sections: List[Dict[str, Any]] = []
    for index, heading in enumerate(headings):
        next_chapter = int(headings[index + 1]["start"]) if index + 1 < len(headings) else None
        next_boundary = next((start for start in boundaries if start > int(heading["start"])), None)
        ends = [value for value in (next_chapter, next_boundary) if value is not None]
        sections.append(
            {
                "heading": heading,
                "start": int(heading["start"]),
                "end": min(ends) if ends else None,
                "number": heading["number"],
                "text": heading["text"],
            }
        )
    return sections


def _numbered_specs(blocks: List[Dict[str, Any]], text: str) -> List[Dict[str, Any]]:
    """编号段落（“5 工具调用…”）按编号升序重排。"""
    items: List[Dict[str, Any]] = []
    for block in blocks:
        if block.get("kind") not in {"paragraph", "heading"}:
            continue
        match = re.match(r"^\s*(\d{1,3})[ \t]+(?=\S)", block.get("text") or "")
        if not match:
            continue
        number = int(match.group(1))
        items.append({"block": block, "number": number})

    if len(items) < 2:
        return []

    sections = _chapter_sections(blocks)
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for item in items:
        position = int(item["block"]["start"])
        section_index = -1
        for index, section in enumerate(sections):
            if section["start"] <= position and (
                section["end"] is None or position < section["end"]
            ):
                section_index = index
                break
        grouped.setdefault(section_index, []).append(item)

    specs: List[Dict[str, Any]] = []
    for order, group in enumerate(sorted(grouped.items(), key=lambda pair: pair[0])):
        section_index, group_items = group
        if len(group_items) < 2:
            continue
        current_numbers = [item["number"] for item in group_items]
        if len(set(current_numbers)) != len(current_numbers):
            continue
        sorted_items = sorted(group_items, key=lambda item: item["number"])
        sorted_numbers = [item["number"] for item in sorted_items]
        if current_numbers == sorted_numbers:
            continue
        before = [
            _short(text[int(item["block"]["start"]) : int(item["block"]["end"])])
            for item in group_items
        ]
        after = [
            _short(text[int(item["block"]["start"]) : int(item["block"]["end"])])
            for item in sorted_items
        ]
        specs.append(
            {
                "id": f"structure:numbered:{section_index}:{order}",
                "field": "reorderBlocks",
                "label": "编号顺序重排",
                "reason": f"编号顺序为 {'→'.join(map(str, current_numbers))}，按编号升序调整",
                "confidence": 0.92,
                "before": before,
                "after": after,
                "layout": {
                    "slots": [
                        {"start": int(item["block"]["start"]), "end": int(item["block"]["end"])}
                        for item in group_items
                    ],
                    "texts": [
                        text[int(item["block"]["start"]) : int(item["block"]["end"])]
                        for item in sorted_items
                    ],
                },
                "kind": "reorder",
            }
        )
    return specs


def _question_groups(
    blocks: List[Dict[str, Any]], text: str
) -> List[Dict[str, Any]]:
    """题目组：题干 + 选项 + 答案/解析行。图片、标题、噪声不属于题目组。"""
    groups: List[Dict[str, Any]] = []
    index = 0
    while index < len(blocks):
        block = blocks[index]
        match = re.match(r"^\s*第\s*(\d+)\s*题", block.get("text") or "")
        if block.get("kind") != "question" or not match:
            index += 1
            continue
        qno = int(match.group(1))
        members = [block]
        cursor = index + 1
        while cursor < len(blocks) and blocks[cursor].get("kind") in {
            "option",
            "answer",
            "analysis",
        }:
            members.append(blocks[cursor])
            cursor += 1
        groups.append(
            {
                "qno": qno,
                "start": int(block["start"]),
                "end": int(members[-1]["end"]),
                "members": members,
                "lines": [
                    text[int(member["start"]) : int(member["end"])] for member in members
                ],
            }
        )
        index = cursor
    return groups


def _question_specs(
    blocks: List[Dict[str, Any]], text: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """题目排序 + 答案归属。

    03 的答案标签会写错位置：第3题下面写着“第1题答案 C”，第1题下面写着
    “第3题答案 B”。这里按答案标签里的题号把答案行归回对应题目，再把题目
    按 1/2/3/5 排序。答案正文一个字都不改，只换它所在的题目组。
    """
    groups = _question_groups(blocks, text)
    if len(groups) < 2:
        return [], []
    if len({group["qno"] for group in groups}) != len(groups):
        # 题号重复说明页面本身有另一类问题，不能贸然重排。
        return [], []

    by_qno = {group["qno"]: group for group in groups}
    answers: Dict[int, List[str]] = {}
    for group in groups:
        for member, line in zip(group["members"], group["lines"]):
            if member.get("kind") not in {"answer", "analysis"}:
                continue
            match = re.search(r"第\s*(\d+)\s*题\s*答案", line)
            target = int(match.group(1)) if match else group["qno"]
            if target in by_qno:
                answers.setdefault(target, []).append(line)

    final_lines: Dict[int, List[str]] = {}
    changed_answer = False
    for group in groups:
        qno = group["qno"]
        question_line = group["lines"][0] if group["lines"] else ""
        option_lines = [
            line
            for member, line in zip(group["members"][1:], group["lines"][1:])
            if member.get("kind") == "option"
        ]
        answer_lines = answers.get(qno) or [
            line
            for member, line in zip(group["members"], group["lines"])
            if member.get("kind") in {"answer", "analysis"}
        ]
        original_answers = [
            line
            for member, line in zip(group["members"], group["lines"])
            if member.get("kind") in {"answer", "analysis"}
        ]
        if answer_lines != original_answers:
            changed_answer = True
        final_lines[qno] = [question_line] + option_lines + answer_lines

    ordered = sorted(groups, key=lambda group: group["qno"])
    if [group["qno"] for group in groups] == [group["qno"] for group in ordered] and not changed_answer:
        return [], []

    before = []
    after = []
    for group in groups:
        answer = next(
            (
                line
                for line in final_lines[group["qno"]]
                if re.match(r"^(?:第\s*\d+\s*题\s*)?(答案|解析)", line.strip())
            ),
            "（无答案）",
        )
        before.append(f"第{group['qno']}题：{_short(group['lines'][0], 30)} / {_short(answer, 24)}")
    for group in ordered:
        answer = next(
            (
                line
                for line in final_lines[group["qno"]]
                if re.match(r"^(?:第\s*\d+\s*题\s*)?(答案|解析)", line.strip())
            ),
            "（无答案）",
        )
        after.append(f"第{group['qno']}题：{_short(group['lines'][0], 30)} / {_short(answer, 24)}")

    return [
        {
            "id": "structure:questions",
            "field": "reorderBlocks",
            "label": "题目顺序与答案归属",
            "reason": "题目按题号升序排列，答案按“第N题答案”标签跟随对应题目",
            "confidence": 0.9,
            "before": before,
            "after": after,
            "layout": {
                "slots": [
                    {"start": group["start"], "end": group["end"]} for group in groups
                ],
                "texts": [
                    "\n".join(final_lines[group["qno"]]) for group in ordered
                ],
            },
            "kind": "reorder",
        }
    ], []


def _table_like_rows(
    blocks: List[Dict[str, Any]], text: str
) -> List[List[Dict[str, Any]]]:
    """把连续表格行分组；单张表一个数组。"""
    tables: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    previous_end: Optional[int] = None
    for block in blocks:
        if block.get("kind") != "table":
            if current:
                tables.append(current)
                current = []
                previous_end = None
            continue
        start = int(block["start"])
        # build_blocks 不保留空行；两行之间隔了空行时仍视为同一张表，但隔了正文则断开。
        if current and previous_end is not None and start - previous_end > 4:
            tables.append(current)
            current = []
        current.append(block)
        previous_end = int(block["end"])
    if current:
        tables.append(current)
    return tables


def _table_specs(blocks: List[Dict[str, Any]], text: str) -> List[Dict[str, Any]]:
    """表格行按首列编号升序。没有编号列的表原样跳过。"""
    specs: List[Dict[str, Any]] = []
    for table_index, rows in enumerate(_table_like_rows(blocks, text)):
        if len(rows) < 2:
            continue
        header: Optional[Dict[str, Any]] = None
        data_rows = rows
        first_text = rows[0].get("text") or ""
        first_cell = _first_cell(first_text)
        if not first_cell.isdigit():
            header = rows[0]
            data_rows = rows[1:]

        numeric_rows: List[Tuple[int, Dict[str, Any]]] = []
        for row in data_rows:
            row_text = row.get("text") or ""
            if _TABLE_SEPARATOR_RE.match(row_text):
                continue
            cell = _first_cell(row_text)
            if cell.isdigit():
                numeric_rows.append((int(cell), row))
            else:
                numeric_rows = []
                break
        if len(numeric_rows) < 2:
            continue
        numbers = [number for number, _ in numeric_rows]
        sorted_rows = [row for _, row in sorted(numeric_rows, key=lambda pair: pair[0])]
        if numbers == [number for number, _ in sorted(numeric_rows, key=lambda pair: pair[0])]:
            continue
        slots = [{"start": int(row["start"]), "end": int(row["end"])} for _, row in numeric_rows]
        texts = [
            text[int(row["start"]) : int(row["end"])] for row in sorted_rows
        ]
        before = [_short(row.get("text") or "") for _, row in numeric_rows]
        after = [_short(row.get("text") or "") for row in sorted_rows]
        specs.append(
            {
                "id": f"structure:table:{table_index}",
                "field": "reorderBlocks",
                "label": "表格行按编号排序",
                "reason": f"表格行编号为 {'→'.join(map(str, numbers))}，按编号升序排序",
                "confidence": 0.9,
                "before": before,
                "after": after,
                "layout": {"slots": slots, "texts": texts},
                "kind": "reorder",
            }
        )
    return specs


def _first_cell(row: str) -> str:
    parts = [part.strip() for part in (row or "").strip().strip("|").split("|")]
    return parts[0] if parts else ""


def _chapter_order_specs(blocks: List[Dict[str, Any]], text: str) -> List[Dict[str, Any]]:
    """章节号乱序时，按章节号重排整节（标题 + 本节正文）。"""
    sections = _chapter_sections(blocks)
    if len(sections) < 2:
        return []
    numbers = [section["number"] for section in sections]
    ordered = sorted(sections, key=lambda section: section["number"])
    if numbers == [section["number"] for section in ordered]:
        return []
    slots = []
    for section in sections:
        end = section["end"] if section["end"] is not None else len(text)
        slots.append({"start": section["start"], "end": end})
    texts = []
    for section in ordered:
        end = section["end"] if section["end"] is not None else len(text)
        texts.append(text[section["start"] : end])
    return [
        {
            "id": "structure:chapter-order",
            "field": "reorderBlocks",
            "label": "章节顺序重排",
            "reason": f"章节顺序为 {'→'.join(map(str, numbers))}，按章节号升序调整",
            "confidence": 0.88,
            "before": [_short(section["text"], 36) for section in sections],
            "after": [_short(section["text"], 36) for section in ordered],
            "layout": {"slots": slots, "texts": texts},
            "kind": "reorder",
        }
    ]


def _chapter_move_specs(blocks: List[Dict[str, Any]], text: str) -> List[Dict[str, Any]]:
    """章节被附录/参考文献隔开时，把章节移回附录之前。

    07 的正文顺序是“第一章 → 第二章 → 附录A → 参考文献 → 第三章”，
    目标顺序是“第一 → 第二 → 第三 → 附录A → 参考文献”。
    """
    sections = _chapter_sections(blocks)
    if len(sections) < 2:
        return []
    boundaries = [
        block
        for block in blocks
        if block.get("kind") == "heading"
        and _SECTION_BOUNDARY_RE.match(block.get("text") or "")
    ]
    if not boundaries:
        return []

    specs: List[Dict[str, Any]] = []
    for index, section in enumerate(sections):
        if index == 0:
            continue
        previous = sections[index - 1]
        heading_start = section["start"]
        if heading_start <= previous["start"]:
            continue
        boundary_after_previous = next(
            (
                block
                for block in boundaries
                if int(block["start"]) > previous["start"]
                and int(block["start"]) < heading_start
            ),
            None,
        )
        if not boundary_after_previous:
            continue
        source_end = section["end"] if section["end"] is not None else len(text)
        specs.append(
            {
                "id": f"structure:chapter-move:{index}",
                "field": "moveBlock",
                "label": "章节顺序调整",
                "reason": (
                    f"「{_short(section['text'], 24)}」出现在附录/参考文献之后，"
                    f"移回章节区，保持正文顺序与目录一致"
                ),
                "confidence": 0.88,
                "before": [
                    f"原位置：附录/参考文献之后（{_short(section['text'], 24)}）"
                ],
                "after": [
                    f"新位置：第{previous['number']}章之后、{_short(boundary_after_previous['text'], 20)}之前"
                ],
                "layout": {
                    "move": {
                        "source": {"start": heading_start, "end": source_end},
                        "target": {
                            "start": int(boundary_after_previous["start"]),
                            "end": int(boundary_after_previous["end"]),
                        },
                        "position": "before",
                    }
                },
                "kind": "move",
            }
        )
    return specs


def duplicate_heading_suggestions(
    blocks: List[Dict[str, Any]], text: str
) -> List[Dict[str, Any]]:
    """连续重复的标题只作为剔除建议，不自动删除。"""
    suggestions: List[Dict[str, Any]] = []
    previous: Optional[Dict[str, Any]] = None
    for block in blocks:
        if block.get("kind") != "heading":
            previous = None
            continue
        if previous is not None:
            same = re.sub(r"\s+", "", previous.get("text") or "") == re.sub(
                r"\s+", "", block.get("text") or ""
            )
            adjacent = int(block["start"]) - int(previous["end"]) <= 2
            if same and adjacent:
                suggestions.append(
                    {
                        "id": f"exclude:duplicate-heading:{len(suggestions)}",
                        "start": int(block["start"]),
                        "end": int(block["end"]),
                        "text": _short(block.get("text") or ""),
                        "reason": "与上一行标题完全重复，疑似重复粘贴",
                        "confidence": 0.92,
                    }
                )
        previous = block
    return suggestions


def layout_ranges(layout: Dict[str, Any]) -> List[Tuple[int, int]]:
    """返回一个布局操作触及的原文范围（用于预览阶段过滤冲突项）。"""
    ranges: List[Tuple[int, int]] = []
    if not isinstance(layout, dict):
        return ranges
    if "slots" in layout:
        for slot in layout.get("slots") or []:
            if isinstance(slot, dict) and slot.get("start") is not None:
                ranges.append((int(slot["start"]), int(slot.get("end", slot["start"]))))
    move = layout.get("move")
    if isinstance(move, dict):
        source = move.get("source") or {}
        target = move.get("target") or {}
        if source.get("start") is not None:
            ranges.append((int(source["start"]), int(source.get("end", source["start"]))))
        if target.get("start") is not None:
            # 目标只占一个插入点，用零宽范围表示，避免误伤目标块本身。
            ranges.append((int(target["start"]), int(target["start"])))
    return ranges


def apply_layouts(raw: str, layouts: List[Dict[str, Any]]) -> str:
    """把多个布局操作应用到原文；槽位替换按 start 倒序执行，避免偏移漂移。

    只允许互不重叠的槽位。若两个整理项都要改同一段文字，说明计划冲突，
    直接报错让用户分开应用，而不是静默丢掉一项。
    """
    text = raw or ""
    replacements: List[Tuple[int, int, str]] = []
    moves: List[Dict[str, Any]] = []
    for layout in layouts or []:
        if not isinstance(layout, dict):
            continue
        if "slots" in layout and "texts" in layout:
            slots = layout.get("slots") or []
            texts = layout.get("texts") or []
            if len(slots) != len(texts):
                raise ValueError("整理布局的槽位数量不一致")
            for slot, value in zip(slots, texts):
                start, end = int(slot.get("start", -1)), int(slot.get("end", -1))
                if start < 0 or end < start or end > len(text):
                    raise ValueError("整理布局的正文范围无效")
                replacements.append((start, end, str(value)))
        elif isinstance(layout.get("move"), dict):
            moves.append(layout["move"])

    replacements.sort(key=lambda item: item[0], reverse=True)
    occupied: List[Tuple[int, int]] = []
    for start, end, value in replacements:
        for other_start, other_end in occupied:
            if start < other_end and end > other_start:
                raise ValueError("两个整理项修改了同一段正文，请分开应用")
        occupied.append((start, end))
        text = text[:start] + value + text[end:]

    # 移动操作按源位置倒序，先处理文末的移动，前面的偏移才不会失效。
    moves.sort(key=lambda item: int(item.get("source", {}).get("start", 0)), reverse=True)
    move_sources: List[Tuple[int, int]] = []
    for move in moves:
        source = move.get("source") or {}
        target = move.get("target") or {}
        source_start = int(source.get("start", -1))
        source_end = int(source.get("end", -1))
        target_start = int(target.get("start", -1))
        if source_start < 0 or source_end <= source_start or source_end > len(text):
            continue
        if target_start < 0 or target_start > len(text):
            continue
        for occupied_start, occupied_end in occupied:
            if source_start < occupied_end and source_end > occupied_start:
                raise ValueError("移动项与重排项修改了同一段正文，请分开应用")
            if occupied_start <= target_start < occupied_end:
                raise ValueError("移动目标落在另一个重排项内，请分开应用")
        for other_start, other_end in move_sources:
            if source_start < other_end and source_end > other_start:
                raise ValueError("两个移动项修改了同一段正文，请分开应用")
            if other_start <= target_start < other_end:
                raise ValueError("移动目标落在另一个移动项内，请分开应用")
        move_sources.append((source_start, source_end))
        segment = text[source_start:source_end]
        if not segment:
            continue
        position = str(move.get("position") or "before")
        if position == "before" and not segment.endswith(("\n", "\r")):
            segment += "\n"
        working = text[:source_start] + text[source_end:]
        insert_at = target_start
        if target_start > source_end:
            insert_at -= source_end - source_start
        if source_start < target_start < source_end:
            continue
        insert_at = max(0, min(insert_at, len(working)))
        text = working[:insert_at] + segment + working[insert_at:]
    return text


def build_structure_plan(
    text: str, structure: Optional[list] = None
) -> Dict[str, Any]:
    """返回 `{"changes": [...], "suggestions": [...]}`。"""
    blocks = build_blocks(text or "", structure)
    changes: List[Dict[str, Any]] = []
    changes.extend(_numbered_specs(blocks, text or ""))
    question_changes, _ = _question_specs(blocks, text or "")
    changes.extend(question_changes)
    changes.extend(_table_specs(blocks, text or ""))
    chapter_order = _chapter_order_specs(blocks, text or "")
    if chapter_order:
        changes.extend(chapter_order)
    else:
        changes.extend(_chapter_move_specs(blocks, text or ""))
    return {
        "changes": changes,
        "suggestions": duplicate_heading_suggestions(blocks, text or ""),
    }
