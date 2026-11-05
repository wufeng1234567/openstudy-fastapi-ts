"""资料装配：把「选中的章节」组装成给 LLM 的装配任务。

为什么单独放在 service：
  · 旧版 StudyPackPanel 在浏览器本地做 `slice(0, 300)` / 「标题 + 首句」，
    算法只能做裁剪，遇到多栏、公式、图片、跨节关系就会漏东西；
  · 现在由后端把选中章节的**完整原文**交给 LLM，前端只负责选择和预览；
  · 章节选择、模式说明、用户额外要求都属于「装配任务」的一部分，
    集中在服务层，便于测试和以后增加新的资产形态。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

MODE_LABELS: Dict[str, str] = {
    "review": "复习卡",
    "lecture": "讲义",
    "outline": "提纲",
}

MODE_GUIDES: Dict[str, str] = {
    "review": (
        "输出「复习卡」：按章节生成主动回忆卡。每张卡包含一个明确的问题、"
        "一个只依据原文的答案，以及一句原文依据（用章节名或【图N】标记定位）。"
        "重点提炼概念、公式、易错点和容易混淆的对比；不要把原文整段照抄。"
    ),
    "lecture": (
        "输出「学习讲义」：按章节组织成可阅读的讲义。每节先说明这一节解决什么问题，"
        "再整理核心概念、关键推导或例题、易错点和小结。保留原文中的公式、步骤和例子，"
        "把零散原文组织成有前后关系的讲解；不要补写原文没有的背景。"
    ),
    "outline": (
        "输出「学习提纲」：按章节生成层级清楚的提纲。列出核心概念、关键公式、"
        "概念之间的关系和复习顺序；每条提纲都要能对应回原文内容，"
        "不要只摘首句，也不要把原文压缩成没有信息量的标题列表。"
    ),
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def select_sections(report: Dict[str, Any], section_indexes: Iterable[int] | None) -> List[Dict[str, Any]]:
    """按前端传来的 sectionIndex 取章节；空选择表示整份资料。"""
    sections = [s for s in (report.get("sections") or []) if isinstance(s, dict)]
    wanted = {_safe_int(x, -1) for x in (section_indexes or [])}
    if not wanted:
        # 「开篇」只是文档开头的零散段落，单独成节价值不高；有正式章节时默认跳过。
        meaningful = [s for s in sections if str(s.get("title") or "") != "开篇"]
        return meaningful or sections
    selected = [s for s in sections if _safe_int(s.get("index"), -1) in wanted]
    return selected


def section_text(raw: str, section: Dict[str, Any]) -> str:
    """按体检报告里的字符区间取章节原文，并做边界保护。"""
    text = str(raw or "")
    start = max(0, min(len(text), _safe_int(section.get("start"), 0)))
    end = max(start, min(len(text), _safe_int(section.get("end"), len(text))))
    return text[start:end].strip()


def build_study_pack_prompt(
    *,
    doc_name: str,
    raw: str,
    report: Dict[str, Any],
    mode: str,
    section_indexes: Iterable[int] | None = None,
    instruction: str = "",
) -> Tuple[str, List[Dict[str, Any]]]:
    """组装 LLM 的 user prompt。

    Returns:
        (prompt, selected_sections)
    """
    normalized_mode = (mode or "review").strip().lower()
    if normalized_mode not in MODE_LABELS:
        normalized_mode = "review"
    sections = select_sections(report, section_indexes)
    if not sections:
        raise ValueError("没有可装配的章节，请先选择至少一个章节")

    blocks: List[str] = []
    for section in sections:
        title = str(section.get("title") or "未命名章节").strip()
        text = section_text(raw, section)
        if not text:
            text = "（原文这一节没有可读取的正文，不要补写。）"
        blocks.append(f"### 章节：{title}\n{text}")

    user_instruction = (instruction or "").strip()
    if not user_instruction:
        user_instruction = "没有额外要求，按通用学习场景生成。"

    prompt = f"""资料名称：{doc_name or '未命名资料'}
生成形态：{MODE_LABELS[normalized_mode]}
用户额外要求：{user_instruction}

【生成要求】
{MODE_GUIDES[normalized_mode]}
请覆盖下面列出的每一个章节，不要跳过任何一节；只使用这些原文，不要引入外部知识。

【选中章节与原文】
{chr(10).join(blocks)}

【输出格式】
直接输出 Markdown 正文。第一行写资产标题，随后按章节组织内容。
复习卡每张卡使用“问题 / 答案 / 原文依据”三个小标题；讲义和提纲使用清晰的章节层级。
不要输出“以下是”“希望对你有帮助”这类套话，不要输出 JSON。"""
    return prompt, sections


__all__ = [
    "MODE_LABELS",
    "MODE_GUIDES",
    "select_sections",
    "section_text",
    "build_study_pack_prompt",
]
