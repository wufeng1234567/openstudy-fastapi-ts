"""
文档编排引擎：解析层（混乱内容 → DocumentSpec）

============================================================================
它解决什么
============================================================================

用户的原话：

    「用户给我们一段文字 或者 一个混乱的word 图文混乱
      我们可以给他进行优化重构 等操作」

"混乱"具体长什么样，是从真实场景总结出来的：

  ① **标题层级混乱**：全文都是正文，或者一大堆 `#`，或者用「一、」「1.」
     混着当标题，没有统一层级
  ② **段落粘连**：整篇一大坨，几十行没有分段；或者反过来，
     一句话一行的硬换行（从 PDF 复制出来最典型）
  ③ **列表被打散**：`- xxx` 和 `1. xxx` 混用；或者项目符号变成了
     裸字符 `•` / `·` / `－`
  ④ **表格是伪表格**：用空格对齐、用 `|` 但没分隔行、
     或者干脆是 `名称    数量    单价` 这种制表符对齐
  ⑤ **图片位置丢失**：图片被塞到文末（Word 里浮动图片被抽取时常见），
     或者只留一句 `[图片]`
  ⑥ **空行滥用**：连续 5 个空行、每段之间夹 3 个空行
  ⑦ **全角/半角混排**：中文里夹英文标点，或者全角空格

============================================================================
处理策略
============================================================================

**保守优先**：只做"几乎不可能出错"的规范化，宁少不错。

会做的：
  · 合并多余空行、去掉行尾空格
  · 识别并统一标题层级（`#` 数量 / 「一、」「（一）」「1.1」按层级推断）
  · 识别列表（含裸字符 `•`）
  · 把"伪表格"（制表符/多空格对齐）转成真表格
  · 把粘连的长段落按句号切成合理段落
  · 图片按出现的先后插入（而不是堆到文末）

**不会做的**（宁可留给 AI 判断，也不能瞎猜）：
  · 不改写文字内容（不做同义替换、不加过渡句）
  · 不猜测图片该配什么图注
  · 不合并看起来相似的两个标题
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.services.doc_compose_model import Block, DocumentSpec

# ============================================================
# 正则
# ============================================================

_RE_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")

# 中文编号标题：「一、」「（一）」「1.1」「第一章」
_RE_CN_NUM_HEAD = re.compile(
    r"^(第[一二三四五六七八九十百]+[章节篇部分]|[一二三四五六七八九十]+[、.．]|[（(][一二三四五六七八九十]+[)）])\s*(.+)$"
)
# 阿拉伯多级编号：「1.」「1.1」「1.1.1」，后接标题性文字
_RE_NUM_HEAD = re.compile(r"^(\d+(?:\.\d+){0,3})[.．、]?\s+(\S.{0,60})$")

# 列表：有序 / 无序（含裸符号）
_RE_LIST = re.compile(r"^(\s*)([-*+•·▪◦○●]|\d+[.)．、])\s+(.+)$")

# 分隔线
_RE_DIVIDER = re.compile(r"^\s*([-*_]\s*){3,}$")

# 引用
_RE_QUOTE = re.compile(r"^>\s?(.*)$")

# 代码围栏
_RE_FENCE = re.compile(r"^```")

# 独立公式块
_RE_MATH_BLOCK = re.compile(r"^\s*\$\$(.+?)\$\$\s*$")
_RE_MATH_BRACKET = re.compile(r"^\s*\\\[(.+?)\\\]\s*$")

# 图片（Markdown 语法 或 单独一行的图片占位）
_RE_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_RE_IMAGE_PLACEHOLDER = re.compile(r"^\[?(图片|image|figure|图\s*\d+)\]?$", re.I)

# 提示框（AI 输出里常见）
_RE_CALLOUT = re.compile(r"^>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(.*)$", re.I)

# 伪表格：制表符分隔 或 3+ 空格分隔，且至少 2 列、连续 2 行以上
_RE_TAB_ROW = re.compile(r"\S(?:\t+\S| {3,}\S)")


# ============================================================
# 入口
# ============================================================

def parse_markdown(
    raw: str,
    *,
    title: str = "",
    theme: str = "clean",
    cover: bool = False,
    toc: bool = False,
) -> DocumentSpec:
    """把一段（可能很乱的）Markdown / 纯文本解析成 DocumentSpec

    Args:
        raw:   原始文本
        title: 文档标题；不传则尝试从第一个标题推断
        theme: 主题名
        cover: 是否生成封面
        toc:   是否生成目录

    Returns:
        DocumentSpec
    """
    text = _normalize_newlines(raw or "")
    lines = text.split("\n")

    blocks: List[Block] = []
    detected_title = ""

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # ── 空行 ──
        if not stripped:
            i += 1
            continue

        # ── 代码围栏 ──
        if _RE_FENCE.match(stripped):
            body, i = _consume_fence(lines, i)
            blocks.append(Block(type="code", text=body))
            continue

        # ── 独立公式块 ──
        m = _RE_MATH_BLOCK.match(stripped) or _RE_MATH_BRACKET.match(stripped)
        if m:
            blocks.append(Block(type="math", text=m.group(1).strip()))
            i += 1
            continue

        # ── 分隔线 ──
        if _RE_DIVIDER.match(stripped):
            blocks.append(Block(type="divider"))
            i += 1
            continue

        # ── 提示框 ──
        m = _RE_CALLOUT.match(stripped)
        if m:
            tone_map = {
                "note": "info", "tip": "success", "important": "info",
                "warning": "warn", "caution": "warn",
            }
            tone = tone_map.get(m.group(1).lower(), "info")
            body, i = _consume_quote(lines, i + 1)
            blocks.append(Block(type="callout", tone=tone, text=(m.group(2) + "\n" + body).strip()))
            continue

        # ── 引用 ──
        if _RE_QUOTE.match(stripped):
            body, i = _consume_quote(lines, i)
            if body.strip():
                blocks.append(Block(type="quote", text=body.strip()))
            continue

        # ── Markdown 标题 ──
        m = _RE_MD_HEADING.match(stripped)
        if m:
            level = min(len(m.group(1)), 4)
            content = m.group(2).strip()
            if not detected_title and level == 1:
                detected_title = content
            blocks.append(Block(type="heading", level=level, text=content))
            i += 1
            continue

        # ── 表格（连续以 | 开头的行）──
        if stripped.startswith("|"):
            table, i = _consume_pipe_table(lines, i)
            if table:
                blocks.append(Block(type="table", table=table))
            continue

        # ── 图片（独占一行）──
        mimg = _RE_MD_IMAGE.search(stripped)
        if mimg and stripped.startswith("!["):
            alt, src = mimg.group(1).strip(), mimg.group(2).strip()
            blocks.append(Block(type="image", image={"src": src, "caption": alt}))
            i += 1
            continue
        if _RE_IMAGE_PLACEHOLDER.match(stripped):
            blocks.append(Block(type="image", image={"src": "", "caption": ""}))
            i += 1
            continue

        # ── 列表（可能连续多行）──
        if _RE_LIST.match(line):
            lst, i = _consume_list(lines, i)
            if lst:
                blocks.append(lst[0])
                # 嵌套层级不同的列表会被拆成多个 block（渲染时缩进表现一致）
                for extra in lst[1:]:
                    blocks.append(extra)
            continue

        # ── 伪表格（制表符 / 多空格对齐）──
        if _RE_TAB_ROW.search(line):
            table, i = _consume_pseudo_table(lines, i)
            if table:
                blocks.append(Block(type="table", table=table))
                continue

        # ── 中文编号 / 阿拉伯编号当标题 ──
        head = _detect_numeric_heading(stripped, blocks)
        if head:
            level, content = head
            blocks.append(Block(type="heading", level=level, text=content))
            i += 1
            continue

        # ── 正文段落 ──
        para, i = _consume_paragraph(lines, i)
        if para:
            blocks.extend(_split_long_paragraph(para))

    # ── 收尾：清理 + 定标题 ──
    blocks = _cleanup_blocks(blocks)
    final_title = title or detected_title or _guess_title(blocks)

    return DocumentSpec(
        title=final_title,
        blocks=blocks,
        theme=theme,
        cover=cover,
        toc=toc,
    )


# ============================================================
# 各类块的消费函数
# ============================================================

def _normalize_newlines(s: str) -> str:
    """统一换行 + 去 BOM + 收掉 3 个以上连续空行"""
    s = s.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    # 连续 3+ 空行 → 1 个空行（段落分隔保留一个就够）
    s = re.sub(r"\n{3,}", "\n\n", s)
    # 行尾空格
    s = "\n".join(ln.rstrip() for ln in s.split("\n"))
    return s


def _consume_fence(lines: List[str], start: int) -> Tuple[str, int]:
    """消费代码块（``` 开头，到下一个 ``` 结束）"""
    i = start + 1
    body: List[str] = []
    while i < len(lines) and not _RE_FENCE.match(lines[i].strip()):
        body.append(lines[i])
        i += 1
    return "\n".join(body), i + 1


def _consume_quote(lines: List[str], start: int) -> Tuple[str, int]:
    """消费连续的 `>` 引用行"""
    i = start
    body: List[str] = []
    while i < len(lines):
        m = _RE_QUOTE.match(lines[i].strip())
        if not m:
            break
        body.append(m.group(1))
        i += 1
    return "\n".join(body), i


def _consume_pipe_table(lines: List[str], start: int) -> Tuple[Optional[Dict[str, Any]], int]:
    """消费 `| a | b |` 形式的表格

    兼容两种写法：
      · 标准：表头 + `|---|---|` 分隔 + 数据行
      · 不标准：直接就是数据行（没有分隔行）→ 第一行当表头
    """
    i = start
    rows: List[List[str]] = []
    align: List[str] = []

    while i < len(lines):
        s = lines[i].strip()
        if not s.startswith("|"):
            break
        cells = _split_pipe_row(s)
        # 分隔行 `|---|---|` 或 `|:--:|--:|`
        if cells and all(re.fullmatch(r":?-{2,}:?", c.strip()) for c in cells if c.strip()):
            align = [_align_of(c) for c in cells]
            i += 1
            continue
        if cells:
            rows.append(cells)
        i += 1

    if not rows:
        return None, i

    headers = rows[0]
    body = rows[1:] if len(rows) > 1 else []

    # 列数对齐（补空 / 截断），否则渲染时会错位
    width = max(len(headers), max((len(r) for r in body), default=0))
    headers = _pad_row(headers, width)
    body = [_pad_row(r, width) for r in body]

    return {"headers": headers, "rows": body, "align": align or ["left"] * width}, i


def _split_pipe_row(s: str) -> List[str]:
    """拆 `| a | b |`；转义 `\\|` 不拆"""
    s = s.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    parts = re.split(r"(?<!\\)\|", s)
    return [p.strip().replace("\\|", "|") for p in parts]


def _align_of(cell: str) -> str:
    c = cell.strip()
    if c.startswith(":") and c.endswith(":"):
        return "center"
    if c.endswith(":"):
        return "right"
    return "left"


def _pad_row(row: List[str], width: int) -> List[str]:
    if len(row) < width:
        return row + [""] * (width - len(row))
    return row[:width]


def _consume_list(lines: List[str], start: int) -> Tuple[List[Block], int]:
    """消费连续列表行

    产出可能多于一个 Block：有序和无序被拆开（渲染时编号规则不同）。
    同一列表内按缩进分成两级（够用；更深的嵌套在 AI 生成内容里极少）。
    """
    i = start
    ordered_items: List[Any] = []
    unordered_items: List[Any] = []
    current_ordered: Optional[bool] = None

    while i < len(lines):
        m = _RE_LIST.match(lines[i])
        if not m:
            break
        indent, marker, content = m.group(1), m.group(2), m.group(3)
        is_ordered = bool(re.match(r"\d", marker))
        depth = 0 if len(indent) < 2 else 1

        item = content.strip() if depth == 0 else {"text": content.strip(), "depth": depth}

        if current_ordered is None:
            current_ordered = is_ordered
        if is_ordered != current_ordered:
            # 类型切换：把已收集的收成一个 block，重新开一个
            break

        (ordered_items if is_ordered else unordered_items).append(item)
        i += 1

    out: List[Block] = []
    if ordered_items:
        out.append(Block(type="list", ordered=True, items=ordered_items))
    if unordered_items:
        out.append(Block(type="list", ordered=False, items=unordered_items))
    return out, i


def _consume_pseudo_table(lines: List[str], start: int) -> Tuple[Optional[Dict[str, Any]], int]:
    """把「制表符 / 多空格对齐」的伪表格转成真表格

    这是从 Word/PDF 复制粘贴最常见的形态：

        名称        数量      单价
        苹果        10        5.0
        香蕉        20        3.5

    ⚠️ 判定门槛要高，否则会把普通段落误判成表格：
       · 至少 2 行
       · 每行的列数必须一致
       · 每列内容长度不能过长（表格单元格不会是一整句话）

    ⚠️ 空单元格不能丢（2026-10-27 实测踩过）：
       从 Word 复制出来的表经常有「合并单元格残留」——首列为空：

           名称    数量    备注
           甲      10      正常
                   20      同上      ← 首列空（其实是"甲"）
                   30      同上

       最初这里用 `if c.strip()` 过滤，于是这一行只剩 2 列，
       「列数一致」判定失败 → **整张表被当成段落**，
       用户在 Word 里看到的是一堆用 Tab 隔开的乱文字。

       正确做法：**保留空单元格**（split 后不丢），只去掉"整行都空"的尾部。
    """
    i = start
    rows: List[List[str]] = []

    while i < len(lines):
        raw = lines[i]
        if not raw.strip():
            break
        if not _RE_TAB_ROW.search(raw):
            break

        # ⚠️ 只 rstrip 不能 strip：行首那个 Tab 是**空首列的边界标记**，
        #    `"\t20\t同上".strip()` 会变成 `"20\t同上"`，
        #    于是这行只剩 2 列、数据整体左移一位（实测踩过：
        #    结果里出现 `['20', '同上', '']` —— 20 跑到第 1 列去了）。
        #
        # 同样，不做 `if c.strip()` 过滤：那会让空首列彻底消失。
        cells = [c.strip() for c in re.split(r"\t+| {3,}", raw.rstrip())]
        # 砍掉行尾连续的空单元格（排版噪音）；行首的空要留（合并单元格语义）
        while cells and not cells[-1]:
            cells.pop()

        if len(cells) < 2:
            break
        rows.append(cells)
        i += 1

    if len(rows) < 2:
        return None, start

    # 列数一致性：缺列的补空（真实数据里常见），多列的拒绝（不像表格）
    width = max(len(r) for r in rows)
    if width < 2:
        return None, start
    if any(len(r) > width for r in rows):
        return None, start
    rows = [r + [""] * (width - len(r)) for r in rows]

    # 单元格不能太长（超过 24 字基本就是句子，不是表格）
    if any(len(c) > 24 for r in rows for c in r):
        return None, start

    headers = rows[0]
    body = rows[1:]
    return (
        {"headers": headers, "rows": body, "align": ["left"] * len(headers)},
        i,
    )


def _consume_paragraph(lines: List[str], start: int) -> Tuple[str, int]:
    """消费一个段落（到空行 / 特殊结构为止）"""
    i = start
    body: List[str] = []
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            break
        # 遇到任何结构化开头就停
        if (
            _RE_MD_HEADING.match(s)
            or _RE_LIST.match(lines[i])
            or s.startswith("|")
            or s.startswith(">")
            or _RE_FENCE.match(s)
            or _RE_DIVIDER.match(s)
            or _RE_MATH_BLOCK.match(s)
        ):
            break
        body.append(s)
        i += 1
    return "\n".join(body), i


def _split_long_paragraph(text: str) -> List[Block]:
    """把"一整坨"长段落按句子切成若干段

    正文超过 320 字且没有换行时，用户在 Word 里看到的是一堵墙。
    按中文句号 / 问号 / 感叹号切，每 2~3 句成一段。

    ⚠️ 只在**完全没有换行**且**足够长**时处理，
       否则会破坏用户自己分好的段落。
    """
    if "\n" in text or len(text) < 320:
        return [Block(type="paragraph", text=text)]

    sentences = re.split(r"(?<=[。！？!?])\s*", text)
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) < 3:
        return [Block(type="paragraph", text=text)]

    out: List[Block] = []
    buf: List[str] = []
    for s in sentences:
        buf.append(s)
        if len("".join(buf)) >= 180:
            out.append(Block(type="paragraph", text="".join(buf).strip()))
            buf = []
    if buf:
        tail = "".join(buf).strip()
        if out and len(tail) < 40:
            # 尾巴太短就并进上一段，避免出现孤立的一行
            out[-1] = Block(type="paragraph", text=out[-1].text + tail)
        else:
            out.append(Block(type="paragraph", text=tail))
    return out


def _detect_numeric_heading(stripped: str, blocks: List[Block]) -> Optional[Tuple[int, str]]:
    """把「一、」「（一）」「1.1」这类编号行识别成标题

    ⚠️ 层级推断保守：
       · 中文数字（一、/（一））→ level 1 / 2
       · 阿拉伯点号（1. / 1.1 / 1.1.1）→ level = 点数 + 1，封顶 4
       · 必须"短"（<= 40 字）且不以句号结尾，否则多半是句子而不是标题
    """
    if len(stripped) > 40 or stripped.endswith("。"):
        return None

    m = _RE_CN_NUM_HEAD.match(stripped)
    if m:
        marker, content = m.group(1), m.group(2).strip()
        if not content or len(content) > 30:
            return None
        # 已经出现过更高级标题、且这里带括号 → 二级
        level = 1
        if marker.startswith(("（", "(")):
            level = 2
        elif re.match(r"^第[一二三四五六七八九十百]+[章篇部分]", marker):
            level = 1
        elif re.match(r"^第[一二三四五六七八九十百]+节", marker):
            level = 2
        return level, content

    m = _RE_NUM_HEAD.match(stripped)
    if m:
        num, content = m.group(1), m.group(2).strip()
        if not content or len(content) > 30:
            return None
        # 「1.5 元」这种不是标题：数字后紧跟量词/单位
        if re.match(r"^(元|个|人|年|月|日|%|米|kg|克|次|条|项|分|秒)", content):
            return None
        dots = num.count(".")
        level = min(dots + 1, 4)
        return level, content

    return None


# ============================================================
# 收尾清理
# ============================================================

def _cleanup_blocks(blocks: List[Block]) -> List[Block]:
    """去掉空块、合并相邻的同类、修正标题层级跳级"""
    out: List[Block] = []
    for b in blocks:
        if b.type == "paragraph" and not (b.text or "").strip():
            continue
        if b.type == "quote" and not (b.text or "").strip():
            continue
        # 相邻同类标题合并（重复的空标题）
        if b.type == "heading" and out and out[-1].type == "heading" and out[-1].text == b.text:
            continue
        out.append(b)

    # 标题层级不能跳级（h1 后直接 h4 在 Word 里目录会断）
    prev_level = 0
    for b in out:
        if b.type != "heading":
            continue
        if prev_level and b.level > prev_level + 1:
            b.level = prev_level + 1
        prev_level = b.level

    return out


def _guess_title(blocks: List[Block]) -> str:
    """没传标题时，用第一个一级标题；再不行用第一段的前 30 字"""
    for b in blocks:
        if b.type == "heading" and b.level == 1:
            return b.text
    for b in blocks:
        if b.type == "paragraph" and b.text:
            return b.text[:30]
    return ""


# ============================================================
# 从解析后的文件结果构建（DOCX / PDF 上传场景）
# ============================================================

def parse_parsed_file(
    parsed: Dict[str, Any],
    *,
    title: str = "",
    theme: str = "clean",
    cover: bool = False,
    toc: bool = False,
) -> DocumentSpec:
    """把 `file_parser.parse_file()` 的结果转成 DocumentSpec

    这是「用户上传一个混乱 Word，我们重新排版」的入口。

    ⚠️ 关键点：`parsed["blocks"]` 里图片的 `src` 是 data URL
       或 `upload/...` 相对路径，渲染层会原样拿去插图片。
       所以这里**不能丢** src，否则图片会变成空白占位。
    """
    blocks: List[Block] = []
    title_guess = ""

    for raw in parsed.get("blocks") or []:
        if not isinstance(raw, dict):
            continue
        btype = raw.get("type")

        if btype == "text":
            content = (raw.get("content") or "").strip()
            if not content:
                continue
            # 文本块里可能还带 Markdown 结构（标题/列表/表格），再过一遍解析
            sub = parse_markdown(content)
            for sb in sub.blocks:
                if sb.type == "heading" and not title_guess and sb.level == 1:
                    title_guess = sb.text
                blocks.append(sb)

        elif btype == "table":
            headers = raw.get("headers") or []
            rows = raw.get("rows") or []
            if headers or rows:
                width = max(len(headers), max((len(r) for r in rows), default=0))
                blocks.append(
                    Block(
                        type="table",
                        table={
                            "headers": _pad_row([str(h) for h in headers], width) if headers else [""] * width,
                            "rows": [_pad_row([str(c) for c in r], width) for r in rows],
                            "align": raw.get("align") or ["left"] * width,
                        },
                    )
                )

        elif btype == "image":
            # ⚠️ 键名必须认全（2026-10-27 修，这是「Word 里的图片全丢」的直接原因）
            #
            # `file_parser.parse_file()` 产出的图片块长这样：
            #     {"type": "image", "imageUrl": "data:image/png;base64,...",
            #      "imageName": "image1.png", "orderIndex": 2}
            #
            # 而这里原来只认 `src` / `url` —— **两个都不存在**，
            # 于是 `src` 恒为空字符串，渲染层拿到空 src 就画一个空白占位。
            # 用户看到的现象就是「重新排版后的文档里图片全没了」，
            # 而且因为不报错，模型也以为排版成功了。
            src = (
                raw.get("src")
                or raw.get("url")
                or raw.get("imageUrl")      # ← file_parser 实际用的键
                or raw.get("image_url")
                or raw.get("dataUrl")
                or ""
            )
            name = (raw.get("imageName") or raw.get("image_name") or "").strip()
            blocks.append(
                Block(
                    type="image",
                    image={
                        "src": src,
                        # 没有 caption 时用原始文件名兜底，
                        # 至少让用户知道这儿本来有张图（比空白占位好）
                        "caption": (raw.get("caption") or "").strip() or (name if name else ""),
                        "widthCm": raw.get("widthCm") or raw.get("width_cm"),
                    },
                )
            )

    blocks = _cleanup_blocks(blocks)
    return DocumentSpec(
        title=title or title_guess or "",
        blocks=blocks,
        theme=theme,
        cover=cover,
        toc=toc,
    )


# ============================================================
# 诊断：告诉调用方"我改了什么"
# ============================================================

def analyze(raw_markdown: str) -> Dict[str, Any]:
    """分析一段文本的"混乱程度"，并给出修复建议

    给 AI 用：让它先看清输入有多乱，再决定要不要重排。
    也给前端用：可以显示"我帮你整理了 N 处"。
    """
    text = raw_markdown or ""
    lines = text.split("\n")

    issues: List[str] = []
    if re.search(r"\n{3,}", text):
        issues.append("有多处连续空行")
    if len(lines) > 8 and all(ln.strip() and not ln.strip().startswith(("#", "-", "*", ">", "|")) for ln in lines[:8]):
        issues.append("开篇一大段没有结构（无标题/列表）")
    if re.search(r"[•·▪◦○●]", text):
        issues.append("用了裸符号做项目符号")
    if re.search(r"\t", text):
        issues.append("含制表符（可能是对齐的伪表格）")
    if "|" in text and not re.search(r"\|\s*:?-{2,}", text):
        issues.append("有竖线但没有表格分隔行（伪表格）")
    if re.search(r"[，。！？]\s*[，。！？]", text):
        issues.append("有重复标点")
    half_width_in_cn = len(re.findall(r"[\u4e00-\u9fa5]\s*[,;:!?]\s*[\u4e00-\u9fa5]", text))
    if half_width_in_cn >= 3:
        issues.append(f"中文里夹半角标点（{half_width_in_cn} 处）")
    if len(re.findall(r"\n\n", text)) > 0 and len(lines) > 40:
        long_paras = [ln for ln in lines if len(ln) > 400]
        if long_paras:
            issues.append(f"有 {len(long_paras)} 个超长段落（>400 字）")

    spec = parse_markdown(text)
    return {
        "issues": issues,
        "issueCount": len(issues),
        "blocks": len(spec.blocks),
        "blockTypeCounts": _count_types(spec),
        "headingLevels": spec.heading_levels(),
        "charCount": len(text),
        "detectedTitle": spec.title,
    }


def _count_types(spec: DocumentSpec) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for b in spec.blocks:
        counts[b.type] = counts.get(b.type, 0) + 1
    return counts
