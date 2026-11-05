"""文档体检：把「这份资料到底哪里能整理/哪里能学」算成可解释的体检报告。

为什么单独做这一层
==================
智能整理原来是一个黑盒动作：用户点一下，等一会儿，看到一份 diff。
但用户真正想知道的是 **为什么要整理、整理完能变成什么**。

这个模块不调用模型，全部指标都由原文规则计算，原因有三：
  · 体检必须可复现：同一份资料两次体检得到同一个分数；
  · 每个分数都要能解释：点开指标能看到它由哪些标题/图片/题目算出来；
  · 体检是整理的入口，不能让模型幻觉决定"要不要整理"。

它输出四类东西：
  1. 四个维度的分数 + 证据（结构 / 图文 / 知识覆盖 / 可学习化）；
  2. 问题清单（带 P0/P1/P2、修复动作）；
  3. 章节级覆盖热力（P1 的「知识覆盖热力图」直接消费这份数据）；
  4. 可出题点、图片归属等编辑需要的统计。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.services.material_organizer import (
    build_blocks,
    duplicate_blocks,
    garbage_blocks,
    image_layout,
    noise_blocks,
    off_topic_blocks,
)
from app.services.outline_tree_service import _extract_headings

#: 一个章节少于这个「字」数，视为内容过薄（只统计中文/英文词，不数标点）
#: 最终会按整份文档的平均章节长度动态收敛，避免短讲义被一刀切判成「全薄」。
THIN_SECTION_UNITS = 40

#: 超长无标题区块：超过这个字数就开始扣结构分
LONG_SECTION_UNITS = 2000

#: 题目起始行：与 material_organizer 的题库识别保持同一套写法。
_QUESTION_START_RE = re.compile(
    r"^\s*(?:第\s*)?(\d+)\s*(?:[.、](?!\d)|题(?!\s*(?:答案|解析|考点|点评)))\s*[［\[]?"
    r"(单选题|多选题|填空题|简答题|判断题|选择题|计算题|论述题)?[\]\]]?",
    re.MULTILINE,
)

#: 「这一节有没有练习」的弱信号。没有题号时，这些词也说明有练习。
_PRACTICE_HINT_RE = re.compile(
    r"(例题|例\s*\d+|练习|习题|思考题|试一试|巩固训练|课后练习|作业|自测)"
)

#: 公式：与 material_organizer.analyze 的口径一致。
_FORMULA_RE = re.compile(r"\$[^$\n]+\$|\\[a-zA-Z]+")

#: 连续空行/分隔线不算正文。
_BLANK_LINE_RE = re.compile(r"^\s*$")


def _text_units(text: str) -> int:
    """中文按字、英文按词统计；排除标点与 Markdown 符号。"""
    if not text:
        return 0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]+", text))
    return cjk + latin


_CHAPTER_LINE_RE = re.compile(
    r"^\s*第\s*([一二三四五六七八九十百零〇\d]+)\s*(章|节)\s*[：:\s]\s*(.+?)\s*$"
)


def _health_headings(text: str) -> List[Dict[str, Any]]:
    """体检专用的标题识别：比大纲树更严格，宁可少切也不把代码行当章节。

    大纲树为了「尽量画出结构」会接受 `10 0.6782 0.8139` 这类数字行；
    在体检里这会把一份代码作业切成 160 个「章节」，导致覆盖度全是红的。
    这里只保留真正像标题的行：
      · Markdown 标题；
      · 中文序号标题；
      · 数字序号标题，但标题里必须至少有两个中文/英文字符；
      · `第X章 / 第X节`（大纲树原先没覆盖这一种）。
    """
    heads = list(_extract_headings(text))
    known_lines = {int(h.get("line") or 0) for h in heads}
    for line_no, raw in enumerate((text or "").split("\n"), start=1):
        if line_no in known_lines:
            continue
        m = _CHAPTER_LINE_RE.match(raw)
        if not m:
            continue
        title = f"第{m.group(1)}{m.group(2)} {m.group(3)}".strip()
        heads.append(
            {
                "level": 1 if m.group(2) == "章" else 2,
                "title": title[:60],
                "line": line_no,
                "kind": "chapter",
            }
        )

    filtered: List[Dict[str, Any]] = []
    for head in heads:
        title = str(head.get("title") or "").strip()
        if not title:
            continue
        if head.get("kind") == "num":
            if len(re.findall(r"[\u4e00-\u9fffA-Za-z]", title)) < 2:
                continue
            if re.fullmatch(r"[\d.,%+\-/\s]+", title):
                continue
        filtered.append(head)
    filtered.sort(key=lambda h: int(h.get("line") or 0))
    return filtered


def _line_offsets(text: str) -> List[int]:
    """返回每一行（1-based line number）在原文中的起始字符偏移。"""
    lines = (text or "").split("\n")
    offsets: List[int] = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    return offsets


def _section_slices(text: str) -> List[Dict[str, Any]]:
    """按标题把正文切成章节；第一个标题前的内容作为「开篇」。"""
    raw = text or ""
    # 章标题只作为层级信息，不单独算一个「内容区块」；否则每个章标题都会
    # 因为只有 8 个字而被判成「内容过薄」，热力图会多出一排无意义的红点。
    heads = [
        h
        for h in _health_headings(raw)
        if not (h.get("kind") == "chapter" and h.get("level") == 1)
    ]
    if not heads:
        return [
            {
                "index": 0,
                "title": "全文",
                "level": 1,
                "start": 0,
                "end": len(raw),
                "text": raw,
            }
        ]

    offsets = _line_offsets(raw)
    starts: List[Tuple[int, Dict[str, Any]]] = []
    for head in heads:
        line_no = int(head.get("line") or 1)
        start = offsets[line_no - 1] if 0 <= line_no - 1 < len(offsets) else 0
        starts.append((start, head))

    sections: List[Dict[str, Any]] = []
    first_start = starts[0][0]
    # 第一个标题前通常只是文档标题/封面，不单独算章节；只有确实是一段导语
    # （超过 120 字）时才保留为「开篇」，避免热力图第一格永远是红色。
    if first_start > 0 and _text_units(raw[:first_start]) >= 120:
        sections.append(
            {
                "index": 0,
                "title": "开篇",
                "level": 1,
                "start": 0,
                "end": first_start,
                "text": raw[:first_start],
            }
        )

    for idx, (start, head) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(raw)
        sections.append(
            {
                "index": len(sections),
                "title": str(head.get("title") or "未命名章节"),
                "level": int(head.get("level") or 1),
                "start": start,
                "end": max(start, end),
                "text": raw[start:end],
            }
        )
    return sections


def _section_payload(section: Dict[str, Any], thin_threshold: int = THIN_SECTION_UNITS) -> Dict[str, Any]:
    text = section.get("text") or ""
    chars = _text_units(text)
    images = len(re.findall(r"【图\d+】", text))
    formulas = len(_FORMULA_RE.findall(text))
    questions = len(_QUESTION_START_RE.findall(text))
    has_practice = questions > 0 or bool(_PRACTICE_HINT_RE.search(text))
    has_explain = chars >= thin_threshold
    if has_explain and has_practice:
        coverage = "good"
        coverage_label = "讲解 + 练习"
    elif has_explain:
        coverage = "partial"
        coverage_label = "有讲解，缺练习"
    else:
        coverage = "thin"
        coverage_label = "内容过薄"
    excerpt = re.sub(r"\s+", " ", re.sub(r"【图\d+】", "", text[:240])).strip()[:90]
    return {
        "index": section["index"],
        "title": section["title"],
        "level": section["level"],
        "start": section["start"],
        "end": section["end"],
        "chars": chars,
        "images": images,
        "formulas": formulas,
        "questions": questions,
        "hasPractice": has_practice,
        "coverage": coverage,
        "coverageLabel": coverage_label,
        "excerpt": excerpt,
    }


def _metric(key: str, label: str, score: int, detail: str, evidence: List[str]) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "score": max(0, min(100, int(round(score)))),
        "detail": detail,
        "evidence": evidence,
    }


def _structure_metric(sections: List[Dict[str, Any]], heading_count: int) -> Dict[str, Any]:
    longest = max((s["chars"] for s in sections), default=0)
    if heading_count == 0:
        return _metric(
            "structure",
            "结构完整度",
            30,
            "未识别到章节标题，全文是一个连续区块",
            ["全文没有可提取的 Markdown / 中文序号 / 数字序号标题"],
        )
    score = 65 + min(25, heading_count * 2)
    penalty = 0
    if longest >= LONG_SECTION_UNITS:
        penalty = min(25, 5 + (longest - LONG_SECTION_UNITS) // 300)
        score -= penalty
    detail = f"识别到 {heading_count} 个标题、{len(sections)} 个内容区块；最长区块 {longest} 字"
    evidence = [f"标题数：{heading_count}", f"最长连续正文：{longest} 字"]
    if penalty:
        evidence.append(f"超长区块扣分：-{penalty}")
    return _metric("structure", "结构完整度", score, detail, evidence)


def _image_metric(doc: Any, raw: str) -> Dict[str, Any]:
    image_map = getattr(doc, "image_map", None) or {}
    asset_total = len(image_map) if isinstance(image_map, dict) else 0
    marker_count = len(re.findall(r"【图\d+】", raw))
    total = max(asset_total, marker_count)
    if total == 0:
        return _metric(
            "image",
            "图文相关度",
            100,
            "文档没有图片，本项不扣分",
            ["未发现图片资产"],
        )
    layout = image_layout(raw)
    irrelevant = [x for x in layout if x.get("status") == "irrelevant"]
    moved = [x for x in layout if x.get("status") == "move"]
    # 图片清单里有、正文里没有【图N】的图 = 根本没插进正文，不能算「能定位」。
    orphan_count = max(0, asset_total - marker_count)
    linked = max(0, marker_count - len(irrelevant) - len(moved))
    score = 100 - (len(irrelevant) + orphan_count) * 18 - len(moved) * 8
    detail = (
        f"共 {total} 张图：{linked} 张能定位到题目/章节，"
        f"{len(moved)} 张位置可疑，{len(irrelevant)} 张找不到归属"
        + (f"，{orphan_count} 张未插入正文" if orphan_count else "")
    )
    evidence = []
    for item in (irrelevant + moved)[:4]:
        evidence.append(f"{item.get('label') or '图片'}：{item.get('reason') or '位置待确认'}")
    if orphan_count:
        evidence.append(f"{orphan_count} 张图片只在资产清单里，正文没有对应位置")
    if not evidence:
        evidence.append("所有图片都能在正文中找到归属")
    return _metric("image", "图文相关度", score, detail, evidence)


def _content_sections(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """去掉「开篇」这种封面/导语区，只统计真正的章节。"""
    return [s for s in sections if s.get("title") != "开篇"] or list(sections)


def _coverage_metric(sections: List[Dict[str, Any]], thin_threshold: int = THIN_SECTION_UNITS) -> Dict[str, Any]:
    content = _content_sections(sections)
    total = len(content)
    if total == 0:
        return _metric("coverage", "知识覆盖度", 40, "没有可分析的章节", ["正文为空"])
    explained = [s for s in content if s["chars"] >= thin_threshold]
    thin = [s for s in content if s["chars"] < thin_threshold]
    score = 100 * len(explained) / total
    detail = (
        f"{total} 个章节中 {len(explained)} 个有完整讲解"
        + (f"；{len(thin)} 个内容过薄" if thin else "")
    )
    evidence = [f"章节总数：{total}", f"有讲解章节：{len(explained)}"]
    if thin:
        evidence.append("内容过薄：" + "、".join(str(s["title"]) for s in thin[:4]))
    return _metric("coverage", "知识覆盖度", score, detail, evidence)


def _learnability_metric(sections: List[Dict[str, Any]], thin_threshold: int = THIN_SECTION_UNITS) -> Dict[str, Any]:
    content = _content_sections(sections)
    total = len(content)
    if total == 0:
        return _metric("learnability", "可学习化程度", 30, "没有可分析的章节", ["正文为空"])
    explained = [s for s in content if s["chars"] >= thin_threshold]
    with_practice = [s for s in content if s["hasPractice"]]
    potential = sum(
        max(1, min(8, (s["chars"] + 119) // 120)) for s in explained
    )
    score = 35 + 40 * (len(with_practice) / total) + min(25, potential // 3)
    detail = (
        f"{len(with_practice)} 个章节带例题/练习；"
        f"按章节内容估算约 {potential} 个可出题点"
    )
    evidence = [
        f"带练习章节：{len(with_practice)} / {total}",
        f"可出题点估算：{potential}",
    ]
    if len(with_practice) < total:
        evidence.append(
            "缺练习：" + "、".join(str(s["title"]) for s in content if not s["hasPractice"])[:120]
        )
    return _metric("learnability", "可学习化程度", score, detail, evidence)


def _grade(overall: int) -> Dict[str, str]:
    if overall >= 85:
        return {"key": "good", "label": "状态良好", "tone": "green"}
    if overall >= 70:
        return {"key": "fair", "label": "基本可用", "tone": "blue"}
    if overall >= 55:
        return {"key": "weak", "label": "建议整理", "tone": "orange"}
    return {"key": "poor", "label": "问题较多", "tone": "red"}


def _issue(
    issue_id: str,
    severity: str,
    category: str,
    title: str,
    detail: str,
    count: int,
    fix_action: str,
) -> Dict[str, Any]:
    return {
        "id": issue_id,
        "severity": severity,
        "category": category,
        "title": title,
        "detail": detail,
        "count": int(count),
        "fixAction": fix_action,
    }


def _issues(
    doc: Any,
    sections: List[Dict[str, Any]],
    metrics: Dict[str, Dict[str, Any]],
    raw: str,
    thin_threshold: int = THIN_SECTION_UNITS,
    heading_count: Optional[int] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if heading_count is None:
        heading_count = sum(1 for s in sections if s["title"] not in ("全文", "开篇"))
    if heading_count == 0:
        out.append(
            _issue(
                "structure:no-heading",
                "P1",
                "结构",
                "全文没有可识别章节标题",
                "正文是一整块连续内容，检索和复习时很难按章节定位。整理时会尝试按题号/段落重建层次。",
                1,
                "organize",
            )
        )

    layout = image_layout(raw)
    irrelevant = [x for x in layout if x.get("status") == "irrelevant"]
    moved = [x for x in layout if x.get("status") == "move"]
    if irrelevant:
        out.append(
            _issue(
                "image:irrelevant",
                "P1",
                "图片",
                f"{len(irrelevant)} 张图片找不到归属",
                "；".join(
                    f"{x.get('label') or '图片'}：{x.get('reason') or '正文中没有对应题目/章节'}"
                    for x in irrelevant[:5]
                ),
                len(irrelevant),
                "organize",
            )
        )
    if moved:
        out.append(
            _issue(
                "image:move",
                "P2",
                "图片",
                f"{len(moved)} 张图片位置可能不对",
                "；".join(
                    f"{x.get('label') or '图片'}：{x.get('reason') or '图片不在对应题目附近'}"
                    for x in moved[:5]
                ),
                len(moved),
                "organize",
            )
        )
    image_map = getattr(doc, "image_map", None) or {}
    asset_total = len(image_map) if isinstance(image_map, dict) else 0
    marker_count = len(re.findall(r"【图\d+】", raw))
    orphan_count = max(0, asset_total - marker_count)
    if orphan_count:
        out.append(
            _issue(
                "image:orphan",
                "P2",
                "图片",
                f"{orphan_count} 张图片没有插入正文",
                "图片资产清单里有文件，但正文中没有对应的【图N】位置，阅读和出题时都不会出现。",
                orphan_count,
                "organize",
            )
        )

    duplicates = duplicate_blocks(raw, getattr(doc, "content_structure", None))
    if duplicates:
        out.append(
            _issue(
                "text:duplicate",
                "P2",
                "正文",
                f"{len(duplicates)} 处重复段落",
                "；".join((x.get("text") or "")[:40] for x in duplicates[:3]),
                len(duplicates),
                "organize",
            )
        )

    noises = noise_blocks(raw, getattr(doc, "content_structure", None))
    garbages = garbage_blocks(raw, getattr(doc, "material_type", None), getattr(doc, "content_structure", None))
    off_topic = off_topic_blocks(raw, getattr(doc, "content_structure", None))
    noise_count = len(noises) + len(garbages) + len(off_topic)
    if noise_count:
        out.append(
            _issue(
                "text:noise",
                "P2",
                "正文",
                f"{noise_count} 处疑似无关内容",
                "包含页码/页眉、格式异常的短文本或与上下文无关的插入句，建议逐条确认。",
                noise_count,
                "organize",
            )
        )

    total_sections = len([s for s in sections if s["title"] != "开篇"])
    with_practice = len([s for s in sections if s["hasPractice"]])
    if total_sections and with_practice == 0:
        out.append(
            _issue(
                "learn:no-practice",
                "P1",
                "学习化",
                "所有章节都没有例题或练习",
                "这份资料更像纯阅读材料；可以按章节生成靶向题，把它变成可练的学习资产。",
                total_sections,
                "questions",
            )
        )
    elif total_sections and with_practice < total_sections:
        missing = total_sections - with_practice
        out.append(
            _issue(
                "learn:partial-practice",
                "P2",
                "学习化",
                f"{missing} 个章节缺少练习",
                "有讲解但没有例题/习题的章节，学完后无法立即自测。",
                missing,
                "questions",
            )
        )

    thin = [s for s in sections if s["chars"] < thin_threshold and s["title"] not in ("开篇",)]
    if thin:
        out.append(
            _issue(
                "structure:thin",
                "P2",
                "结构",
                f"{len(thin)} 个章节内容过薄",
                "、".join(str(s["title"]) for s in thin[:5]),
                len(thin),
                "view",
            )
        )

    longest = max((s["chars"] for s in sections), default=0)
    if longest >= LONG_SECTION_UNITS * 1.25:
        out.append(
            _issue(
                "structure:long",
                "P2",
                "结构",
                "存在超长无标题区块",
                f"最长连续正文 {longest} 字没有标题，阅读时容易迷失位置。",
                1,
                "organize",
            )
        )

    severity_order = {"P0": 0, "P1": 1, "P2": 2}
    out.sort(key=lambda x: (severity_order.get(x["severity"], 9), -int(x["count"])))
    return out


def build_document_health(doc: Any) -> Dict[str, Any]:
    """计算一份文档的体检报告（纯规则、无 LLM）。

    Args:
        doc: `app.models.rag.RagDocument` 实例（也兼容测试用的简单对象）。

    Returns:
        可直接 JSON 序列化的体检报告，前端 `DocumentHealthDialog` 直接消费。
    """
    raw = str(getattr(doc, "raw_content", "") or "")
    raw_sections = _section_slices(raw)
    total_units = _text_units(raw)
    average_units = total_units / max(1, len(raw_sections))
    # 短讲义（平均每节 40 字）不应该被 80 字的固定阈值判成「全薄」。
    thin_threshold = max(THIN_SECTION_UNITS, min(120, round(average_units * 0.55)))
    sections = [_section_payload(s, thin_threshold) for s in raw_sections]
    heading_count = len(_health_headings(raw))
    metrics = {
        "structure": _structure_metric(sections, heading_count),
        "image": _image_metric(doc, raw),
        "coverage": _coverage_metric(sections, thin_threshold),
        "learnability": _learnability_metric(sections, thin_threshold),
    }
    # 权重在 UI 上也要能解释：结构 30% / 图文 20% / 覆盖 25% / 可学习化 25%
    overall = round(
        metrics["structure"]["score"] * 0.30
        + metrics["image"]["score"] * 0.20
        + metrics["coverage"]["score"] * 0.25
        + metrics["learnability"]["score"] * 0.25
    )
    issues = _issues(doc, sections, metrics, raw, thin_threshold, heading_count)
    return {
        "docId": int(getattr(doc, "id", 0) or 0),
        "fileName": str(getattr(doc, "file_name", "") or ""),
        "score": overall,
        "grade": _grade(overall),
        "weights": {"structure": 0.30, "image": 0.20, "coverage": 0.25, "learnability": 0.25},
        "metrics": [metrics["structure"], metrics["image"], metrics["coverage"], metrics["learnability"]],
        "issues": issues,
        "sections": sections,
        "stats": {
            "wordCount": _text_units(raw),
            "headingCount": heading_count,
            "sectionCount": len(sections),
            "imageCount": max(
                len(getattr(doc, "image_map", None) or {}),
                len(re.findall(r"【图\d+】", raw)),
            ),
            "questionCount": sum(s["questions"] for s in sections),
            "practiceSectionCount": len([s for s in sections if s["hasPractice"]]),
            "duplicateCount": len(duplicate_blocks(raw, getattr(doc, "content_structure", None))),
            "noiseCount": len(noise_blocks(raw, getattr(doc, "content_structure", None)))
            + len(garbage_blocks(raw, getattr(doc, "material_type", None), getattr(doc, "content_structure", None)))
            + len(off_topic_blocks(raw, getattr(doc, "content_structure", None))),
        },
        # 给「整理手术台」用的直连建议：体检发现问题后可直接跳到整理预览。
        "organizeSuggested": any(i["fixAction"] == "organize" for i in issues),
    }


def find_section_for_offset(sections: List[Dict[str, Any]], offset: int) -> Optional[Dict[str, Any]]:
    """按字符偏移找章节——后续做「题目 → 原文段落」定位时可复用。"""
    for section in sections:
        if int(section.get("start", 0)) <= offset < int(section.get("end", 0)):
            return section
    return None


__all__ = ["build_document_health", "find_section_for_offset"]
