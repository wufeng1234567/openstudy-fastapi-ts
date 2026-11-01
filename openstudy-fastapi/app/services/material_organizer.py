"""资料智能整理：规则化命名、主题/类型识别和内容 facet。

刻意不调用 LLM：
  · 文件名/正文是用户资料，命名和分类必须可复现；
  · 错一次不能靠“换个提示词”掩盖，规则命中/未命中都看得见；
  · 真正的语义理解（公式、图片、表格）来自 file_parser，不来自模型猜测。

只做「建议」：display_name 只在文件名明显无意义时替换；
subject/material_type 只是 facet，用户仍然可以后续手动改。
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

#: 明显无意义的文件名（不含扩展名）
_GENERIC_NAME_RE = re.compile(
    r"^(新建(?: Microsoft Word|文本文档|文档)?\s*(?:\(\d+\))?|"
    r"未命名(?:文档)?|文档|扫描件\d*|扫描|图片\d*|image\d*|img[_-]?\d*|无标题|test|tmp)$",
    re.IGNORECASE,
)

#: 上传/导出链路常见的 hash 前缀：453905ae0251_概率论...docx
_HASH_PREFIX_RE = re.compile(r"^[0-9a-f]{8,}[_-]+", re.IGNORECASE)

_SUBJECT_RULES = {
    "数学": ("数学", "函数", "方程", "概率", "统计", "微积分", "线性代数", "几何", "三角", "导数", "积分", "矩阵", "向量"),
    "英语": ("英语", "english", "单词", "语法", "听力", "阅读", "写作", "翻译", "完形"),
    "数据结构": ("数据结构", "链表", "二叉树", "红黑树", "图论", "排序", "哈希", "栈", "队列"),
    "计算机网络": ("计算机网络", "tcp", "udp", "http", "ip", "路由", "交换机", "网络协议"),
    "操作系统": ("操作系统", "进程", "线程", "内存管理", "文件系统", "调度", "死锁"),
    "数据库": ("数据库", "sql", "mysql", "postgres", "索引", "事务", "范式"),
    "物理": ("物理", "力学", "电磁", "光学", "热学", "量子", "电路"),
    "化学": ("化学", "元素", "化合物", "反应", "有机", "无机"),
    "地理": ("地理", "等高线", "气候", "洋流", "地形", "经纬"),
}

_TYPE_RULES = (
    ("试卷", ("试卷", "真题", "期末", "期中", "考试", "模拟卷", "答题卡")),
    ("习题", ("习题", "练习", "作业", "题目", "题库")),
    ("讲义", ("讲义", "课件", "课程", "教程", "章节")),
    ("笔记", ("笔记", "记录", "总结", "复习")),
    ("教材", ("教材", "课本", "教科书")),
)


def _first_meaningful_line(text: str) -> str:
    """取正文中第一行像标题的内容；没有就取第一行非空文本。"""
    for raw in (text or "").splitlines():
        line = re.sub(r"^[#*\-\s]+", "", raw).strip()
        if not line or len(line) < 3:
            continue
        if len(line) > 80:
            line = line[:80]
        return line
    return ""


def _summary_text(text: str) -> str:
    """给 diff 面板看的纯文字摘要：不把 LaTeX 源码塞给用户。"""
    s = text or ""
    s = re.sub(r"\$[^$\n]*\$", " ", s)
    s = re.sub(r"\\[a-zA-Z]{2,15}", " ", s)
    s = re.sub(r"[{}$]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:160]


def _suggest_display_name(file_name: str, text: str) -> str:
    stem, ext = os.path.splitext(file_name or "")
    raw_stem = stem.strip()

    # 导出/上传链路常把短 hash 拼在文件名前；这是纯噪声，不只是“不好看”，
    # 还会让用户按名字检索时永远匹配不到正文标题。
    clean_stem = _HASH_PREFIX_RE.sub("", raw_stem).strip()
    if clean_stem and clean_stem != raw_stem and not _GENERIC_NAME_RE.match(clean_stem):
        return f"{clean_stem}{ext}"

    # `新建文档 (3)` / `扫描件001` 这类名字没有信息量，换成正文第一行
    if not _GENERIC_NAME_RE.match(raw_stem):
        return file_name
    candidate = _first_meaningful_line(text)
    if not candidate:
        return file_name
    # 去掉常见题号/章节序号前缀，保留有意义的标题
    candidate = re.sub(r"^[（(]?[一二三四五六七八九十0-9]+[）)、.．]\s*", "", candidate)
    candidate = candidate[:60].strip()
    return f"{candidate}{ext}" if candidate else file_name


_QUESTION_GROUP_RE = re.compile(
    r"^\s*(?:第\s*)?(\d+)\s*(?:[.、]|题(?!\s*(?:答案|解析|考点|点评)))\s*[［\[]?"
    r"(单选题|多选题|填空题|简答题|判断题|选择题|计算题|论述题)?[\]\]]?",
    re.MULTILINE,
)

#: 章节标题：第一章 / 第1章 / 第 二 章。只做“章节”这一级，避免把“第3节”当题目。
_CHAPTER_RE = re.compile(
    r"^\s*第\s*([一二三四五六七八九十百零〇\d]+)\s*章(?:\s|$|[：:])"
)
#: 节标题：第3节 / 第三节。只作为标题保护，不参与章节级重排。
_SECTION_RE = re.compile(
    r"^\s*第\s*([一二三四五六七八九十百零〇\d]+)\s*节(?:\s|$|[：:])"
)
#: 非正文章节边界（目录/附录/参考文献等），用来判断“第三章跑到附录后面了”。
_SECTION_BOUNDARY_RE = re.compile(
    r"^\s*(?:附录|参考文献|致谢|后记|目录)(?:\s|$|[：:A-Za-z0-9])"
)
#: Markdown 表格行（至少两个竖线，避免把普通正文中的 ``|`` 当表格）。
_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|.*\|\s*$")


def question_groups(text: str) -> list[Dict[str, Any]]:
    """题库结构：按题型汇总真实题数，不虚构题型。"""
    groups: Dict[str, Dict[str, Any]] = {}
    for m in _QUESTION_GROUP_RE.finditer(text or ""):
        name = m.group(2) or "题目"
        item = groups.get(name)
        if item:
            item["count"] += 1
            item["first"] = min(item["first"], int(m.group(1)))
        else:
            groups[name] = {"name": name, "count": 1, "first": int(m.group(1))}
    return list(groups.values())


def _structure_hints(structure: Optional[list]) -> dict[str, Dict[str, str]]:
    """把解析器块提示摊平成按行文本索引，供 build_blocks 使用。"""
    hints: dict[str, Dict[str, str]] = {}
    for item in structure or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if kind not in {"code", "formula", "table", "answer"}:
            continue
        text = str(item.get("text") or "")
        for line in text.splitlines():
            key = re.sub(r"\s+", "", line)
            if key:
                hints[key] = {
                    "kind": kind,
                    "language": str(item.get("language") or ""),
                    "confidence": str(item.get("confidence") or ""),
                    "evidence": str(item.get("evidence") or ""),
                }
    return hints


def build_blocks(text: str, structure: Optional[list] = None) -> list[Dict[str, Any]]:
    """把正文切成带稳定偏移的块，供 LLM 只读/可编辑边界标注。

    structure 来自 file_parser 的 contentStructure；用于保护 Word/TXT/PDF
    里没有 Markdown 围栏的代码块，不能只依赖正文正则。
    """
    blocks: list[Dict[str, Any]] = []
    hints = _structure_hints(structure)
    offset = 0
    in_fence = False
    fence_kind = "code"
    dollar_fence = False
    for raw_line in (text or "").splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        if not stripped:
            offset += len(raw_line)
            continue

        # Markdown 围栏代码：开/闭围栏都保留为 code 块，避免围栏本身被当成正文。
        if stripped.startswith("```"):
            in_fence = not in_fence
            fence_kind = "code"
            kind, lock = "code", "READONLY"
        elif in_fence:
            kind, lock = "code", "READONLY"
        # 独立 $$ 公式围栏（04/09 的块公式）：围栏和内部行都保护。
        elif stripped == "$$":
            dollar_fence = not dollar_fence
            kind, lock = "formula", "READONLY"
        elif dollar_fence:
            kind, lock = "formula", "READONLY"
        else:
            hint = hints.get(re.sub(r"\s+", "", line))
            if hint:
                kind = hint["kind"]
                lock = "READONLY" if kind in {"code", "formula", "table", "answer"} else "SUGGEST_ONLY"
            else:
                kind = "paragraph"
                lock = "READONLY"
                if re.match(r"^【图\d+】$", stripped):
                    kind, lock = "image", "SUGGEST_ONLY"
                elif _TABLE_LINE_RE.match(stripped):
                    # 表格行绝不能被当成普通段落删除；排序由结构化整理单独生成。
                    kind, lock = "table", "READONLY"
                elif (
                    _CHAPTER_RE.match(stripped)
                    or _SECTION_RE.match(stripped)
                    or _SECTION_BOUNDARY_RE.match(stripped)
                ):
                    kind, lock = "heading", "EDITABLE"
                elif re.match(r"^(?:第\s*\d+\s*题\s*)?(答案|解析|考点|点评)[：:]", stripped):
                    kind = "answer" if re.match(r"^(?:第\s*\d+\s*题\s*)?答案[：:]", stripped) else "analysis"
                    lock = "READONLY"
                elif _QUESTION_GROUP_RE.match(stripped) and not _CHAPTER_RE.match(stripped):
                    # 题目/选项只允许整体移动，正文仍然只读。
                    kind, lock = "question", "MOVE_ONLY"
                elif re.match(r"^\s*[A-D][.、]\s*", stripped):
                    kind, lock = "option", "MOVE_ONLY"
                elif re.match(r"^(#{1,6}\s+|[一二三四五六七八九十]+[、.．])", stripped):
                    kind, lock = "heading", "EDITABLE"
                elif re.search(r"\$[^$]+\$|\\[a-zA-Z]+", stripped):
                    kind, lock = "formula", "READONLY"
                elif re.match(
                    r"^\s*(?:第\s*\d+\s*页|-\s*\d+\s*-|\d+\s*/\s*\d+|"
                    r"练习题?第\s*\d+\s*页|内部资料[｜|].*第\s*\d+\s*页.*共\s*\d+\s*页)\s*$",
                    stripped,
                ):
                    kind, lock = "noise", "SUGGEST_ONLY"
                elif re.match(r"^(版权所有[，,].*翻印必究[。.]?|内部试用版)$", stripped):
                    kind, lock = "noise", "SUGGEST_ONLY"
                elif re.match(r"^\s*\d{1,3}[ \t]+\S", line):
                    # 纯编号段落（5 工具调用…）只允许整体重排，不能被当作可改写正文。
                    kind, lock = "paragraph", "MOVE_ONLY"
        blocks.append(
            {
                "id": f"B{len(blocks) + 1:04d}",
                "kind": kind,
                "lock": lock,
                "start": offset,
                "end": offset + len(line),
                "text": line,
            }
        )
        offset += len(raw_line)
    return blocks


def image_links(text: str) -> list[str]:
    """按最近题目/标题给图片做“建议关联”，只写结构元数据，不动图片文件。"""
    links: list[str] = []
    current = "正文"
    for block in build_blocks(text):
        line = block.get("text") or ""
        if block.get("kind") == "question":
            current = line[:36]
        elif block.get("kind") == "heading":
            current = line[:36]
        elif block.get("kind") == "image":
            marker = re.search(r"【图(\d+)】", line)
            label = f"图{int(marker.group(1)) + 1}" if marker else line
            links.append(f"{label} → {current}")
    return links


_OFF_TOPIC_HINTS = (
    "阳台", "绿萝", "咖啡", "露营", "旅行", "午餐", "晚饭", "天气",
    "猫咪", "购物", "电影", "音乐", "周末", "奶茶", "蛋糕",
)
_DOMAIN_HINTS = (
    "智能体", "模型", "工具", "记忆", "规划", "检索", "知识", "文档",
    "系统", "任务", "评测", "安全", "推理", "上下文", "检索增强",
    # API/接口举例经常出现“天气/咖啡”等日常词，不能被当成闲聊误删。
    "API", "接口", "调用", "请求", "响应", "缓存", "参数", "函数",
    "数据", "服务", "地图", "天气 API",
)


def is_off_topic_line(line: str) -> bool:
    """判断一段文字是否像误插入的日常闲聊/广告，而不是技术正文。"""
    text = (line or "").strip()
    if len(text) < 8 or len(text) > 120:
        return False
    has_off_topic = any(word in text for word in _OFF_TOPIC_HINTS)
    has_domain = any(word in text for word in _DOMAIN_HINTS)
    return has_off_topic and not has_domain


def off_topic_blocks(text: str, structure: Optional[list] = None) -> list[Dict[str, Any]]:
    """找出中间突然插入的无关日常句子；只建议，不自动删除。"""
    out: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for block in build_blocks(text, structure):
        if block.get("kind") != "paragraph":
            continue
        line = (block.get("text") or "").strip()
        if not is_off_topic_line(line):
            continue
        key = re.sub(r"\s+", "", line)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "target": block["id"],
                "start": block["start"],
                "end": block["end"],
                "text": line[:100],
                "reason": "与上下文无关的日常闲聊/广告，疑似误插入",
                "kind": "offtopic",
            }
        )
    return out


def image_layout(text: str) -> list[Dict[str, Any]]:
    """分析图片在正文中的位置和归属。

    返回每张图片的上下文位置：
    - linked: 图片已经在对应题目附近
    - move: 图片有明确的“第 N 题”指向，但当前不在该题附近
    - irrelevant: 图片在正文/题目之外，找不到归属

    这里只生成建议，最终是否应用由用户确认。
    """
    blocks = build_blocks(text)
    questions = [block for block in blocks if block.get("kind") == "question"]
    # 章节标题/题目是首选锚点；没有标题的图文说明（05）用普通段落兜底，
    # 否则纯知识文档里的图会被全部误判为“无归属”。
    anchors = [block for block in blocks if block.get("kind") in ("question", "heading")]
    if not anchors:
        anchors = [
            block
            for block in blocks
            if block.get("kind") == "paragraph" and len((block.get("text") or "").strip()) >= 8
        ]
    images = [block for block in blocks if block.get("kind") == "image"]
    by_number: Dict[int, Dict[str, Any]] = {}
    for question in questions:
        m = re.match(r"^\s*(?:第\s*)?(\d+)\s*(?:[.、]|题)", question.get("text") or "")
        if m:
            by_number[int(m.group(1))] = question

    out: list[Dict[str, Any]] = []
    for block in images:
        marker = re.search(r"【图(\d+)】", block.get("text") or "")
        if not marker:
            continue
        index = int(marker.group(1))
        start, end = int(block["start"]), int(block["end"])
        prev_anchor = None
        next_anchor = None
        for anchor in anchors:
            if int(anchor["end"]) <= start:
                prev_anchor = anchor
            elif next_anchor is None and int(anchor["start"]) >= end:
                next_anchor = anchor
        context = (text[max(0, start - 260) : start] + text[end : end + 160]) or ""
        # 图片标记可能出现在“图2（对应第1题）”之后，也可能在说明之前。
        caption = (text[max(0, start - 160) : start] + text[end : end + 80]) or ""
        block_pos = blocks.index(block)
        prev_block = blocks[block_pos - 1] if block_pos > 0 else None
        target_no = None
        m_target = re.search(r"第\s*(\d+)\s*题", caption)
        if m_target:
            target_no = int(m_target.group(1))
        target_q = by_number.get(target_no) if target_no else None
        if target_q is None and prev_anchor and prev_anchor.get("kind") == "question":
            target_q = prev_anchor
        has_reference = bool(re.search(r"如图|下图|上图|见图|图\s*\d+|示意图|图片", context))
        off_topic = bool(
            prev_block
            and prev_block.get("kind") == "paragraph"
            and is_off_topic_line(prev_block.get("text") or "")
        )

        status = "linked"
        reason = ""
        if prev_anchor is None and next_anchor is None:
            status = "irrelevant"
            reason = "正文中没有可归属的题目或章节"
        elif prev_anchor is None:
            status = "irrelevant"
            reason = "图片位于第一个章节之前，找不到归属"
        elif off_topic:
            status = "irrelevant"
            reason = "图片紧挨着与上下文无关的日常闲聊，疑似误插入"
        elif target_q and prev_anchor.get("kind") == "question" and int(target_q["start"]) != int(prev_anchor["start"]):
            status = "move"
            reason = f"图片标注指向第{target_no}题，当前却位于{prev_anchor.get('text', '')[:28]}之后"
        elif not has_reference and prev_anchor.get("kind") == "question" and start - int(prev_anchor["end"]) > 500:
            status = "irrelevant"
            reason = "图片距离最近题目过远，且附近没有“如图/下图”等引用"

        out.append(
            {
                "index": index,
                "label": f"图{index + 1}",
                "start": start,
                "end": end,
                "status": status,
                "reason": reason,
                "question": (target_q or prev_anchor or {}).get("text", "")[:60],
                "questionStart": int((target_q or prev_anchor or {}).get("start", start)),
                "questionEnd": int((target_q or prev_anchor or {}).get("end", end)),
                "prevQuestion": (prev_anchor or {}).get("text", "")[:60],
                "hasReference": has_reference,
                "caption": caption.strip()[:80],
            }
        )
    return out


_LOG_LINE_RE = re.compile(
    r"^\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}:\d{2}.*\b(INFO|WARN|WARNING|ERROR|DEBUG)\b"
)


def duplicate_blocks(text: str, structure: Optional[list] = None) -> list[Dict[str, Any]]:
    """找重复段落，只作为剔除建议。"""
    seen: Dict[str, Dict[str, Any]] = {}
    out: list[Dict[str, Any]] = []
    for block in build_blocks(text, structure):
        # 只看较长的普通段落：题干/答案会出现大量正常的重复短句，不能当重复内容。
        if block.get("kind") != "paragraph":
            continue
        # 重复日志是正常现象（重试/并发），不能建议删除。
        if _LOG_LINE_RE.match(block.get("text") or ""):
            continue
        normalized = re.sub(r"\s+", "", block.get("text") or "")
        if len(normalized) < 60:
            continue
        if normalized in seen:
            out.append(
                {
                    "target": block["id"],
                    "start": block["start"],
                    "end": block["end"],
                    "text": (block.get("text") or "").strip()[:80],
                    "reason": "与前面段落重复",
                    "kind": "duplicate",
                }
            )
        else:
            seen[normalized] = block
    return out


def garbage_blocks(
    text: str,
    material_type: Optional[str] = None,
    structure: Optional[list] = None,
) -> list[Dict[str, Any]]:
    """找出疑似手动插入的无关短文本；只做建议，绝不自动删除。

    注意：标题、图片 Markdown、分隔线、页眉页脚都不能算垃圾。
    题号格式检查只用于习题/试卷；知识讲义里的有序列表不能被误判。
    日常闲聊/广告由 off_topic_blocks 单独处理。
    """
    out: list[Dict[str, Any]] = []
    seen: set[str] = set()
    is_exercise = material_type in ("习题", "试卷")
    for block in build_blocks(text, structure):
        if block.get("kind") != "paragraph":
            continue
        line = (block.get("text") or "").strip()
        normalized = re.sub(r"\s+", "", line)
        if len(normalized) < 6 or len(normalized) > 80:
            continue
        if line.startswith("!") or line.startswith("---") or "─" in line or "|" in line:
            continue
        numbered_without_type = bool(re.match(r"^\d+[.、]\s*", line)) and "［" not in line and "[" not in line
        if not is_exercise or not numbered_without_type:
            continue
        key = normalized
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "target": block["id"],
                "start": block["start"],
                "end": block["end"],
                "text": line,
                "reason": "题号格式异常，疑似手动插入的无关文字",
                "kind": "garbage",
            }
        )
    return out


def noise_blocks(text: str, structure: Optional[list] = None) -> list[Dict[str, Any]]:
    """找出可建议剔除的页码/孤立标记；只返回建议，不删除。"""
    suggestions = []
    for block in build_blocks(text, structure):
        if block["kind"] == "noise":
            suggestions.append(
                {
                    "target": block["id"],
                    "start": block["start"],
                    "end": block["end"],
                    "text": (block.get("text") or "").strip()[:80],
                    "reason": "疑似页码/页眉页脚",
                    "kind": "noise",
                }
            )
    return suggestions


def analyze(
    file_name: str,
    text: str,
    parsed: Optional[Dict[str, Any]] = None,
    image_count: int = 0,
) -> Dict[str, Any]:
    """返回可直接写入 RagDocument 的整理结果。"""
    lower = f"{file_name}\n{text}".lower()

    subject = "未分类"
    subject_hits = 0
    for name, keywords in _SUBJECT_RULES.items():
        hits = sum(1 for kw in keywords if kw.lower() in lower)
        if hits > subject_hits:
            subject, subject_hits = name, hits

    material_type = "资料"
    for name, keywords in _TYPE_RULES:
        if any(kw.lower() in lower for kw in keywords):
            material_type = name
            break

    formula_count = len(re.findall(r"\$[^$\n]+\$|\\[a-zA-Z]+", text or ""))
    table_count = len(re.findall(r"(?m)^\s*\|?\s*:?-{3,}", text or ""))
    word_count = len(re.findall(r"[\u4e00-\u9fff]", text or "")) + len(
        re.findall(r"[A-Za-z]+", text or "")
    )
    heading_count = sum(
        1
        for line in (text or "").splitlines()
        if re.match(r"^\s*(?:#{1,6}\s+|[一二三四五六七八九十]+[、.．]|\d+(?:\.\d+)*[、.．]\s*)", line)
        or _CHAPTER_RE.match(line)
        or _SECTION_RE.match(line)
        or _SECTION_BOUNDARY_RE.match(line)
    )
    if parsed:
        blocks = parsed.get("blocks") or []
        table_count = max(
            table_count,
            sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "table"),
        )
        image_count = max(image_count, len(parsed.get("images") or []))
    # Markdown 表格即便没有分隔行，也应按“表格块”而不是行数计入统计。
    markdown_tables = 0
    previous_table_end: Optional[int] = None
    for block in build_blocks(text):
        if block.get("kind") != "table":
            previous_table_end = None
            continue
        if previous_table_end is None or int(block["start"]) - previous_table_end > 4:
            markdown_tables += 1
        previous_table_end = int(block["end"])
    table_count = max(table_count, markdown_tables)

    display_name = _suggest_display_name(file_name, text)
    confidence = min(0.95, 0.35 + subject_hits * 0.1) if subject != "未分类" else 0.25
    summary = _summary_text(text)

    return {
        "display_name": display_name,
        "original_file_name": file_name,
        "subject": subject,
        "material_type": material_type,
        "facets": {
            "subject": subject,
            "materialType": material_type,
            "formulaCount": formula_count,
            "imageCount": image_count,
            "tableCount": table_count,
            "wordCount": word_count,
            "headingCount": heading_count,
            "questionGroups": question_groups(text),
            "summary": summary,
            "confidence": round(confidence, 2),
        },
    }
