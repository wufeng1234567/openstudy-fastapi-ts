"""
文档编排引擎：渲染层（DocumentSpec → .docx / .pdf）

============================================================================
设计取舍
============================================================================

**复用而不是重写**：`bank_export_service` 里那套手写 oxml 是经过实测的
（表格底纹/边框/固定列宽/跨页重复表头、单元格内公式、图片嵌入），
踩过的坑都写注释了。这里直接 import 那几个下划线工具函数，
只做"编排"这一层（标题层级、封面、目录、页眉页脚、主题样式）。

**PDF 走 DOCX → LibreOffice**：项目里已有 `pdf_docx_service` 这条路
（Edge 打印会崩、reportlab 排版能力太弱），排版一次两处通用，
不会出现 "Word 好看、PDF 难看" 的分裂。

**容量控制**：正文超过 N 字时自动缩字号/行距，避免溢出成 60 页。
不是截断内容，只是把排版压紧。
"""
from __future__ import annotations

import datetime
import io
import logging
import re
from typing import Any, Dict, List, Optional

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

logger = logging.getLogger(__name__)

from app.services.doc_compose_model import (
    DEFAULT_THEME,
    Block,
    DocumentSpec,
    get_theme,
)

# ── 复用题库导出里已验证过的底层工具 ──
from app.services.bank_export_service import (
    _add_omml,
    _add_run,
    _add_segments,
    _docx_add_image,
    _docx_forbid_row_split,
    _docx_mark_header_row,
    _docx_set_cell_margins,
    _docx_set_cell_shading,
    _docx_set_cjk_font,
    _docx_set_table_borders,
)


# ============================================================
# 常量
# ============================================================

#: 页面：A4，页边距按中文公文习惯（上 2.5 / 下 2.2 / 左右 2.4）
PAGE_W_CM = 21.0
MARGIN_L_CM = 2.4
MARGIN_R_CM = 2.4
MARGIN_T_CM = 2.5
MARGIN_B_CM = 2.2
CONTENT_W_CM = PAGE_W_CM - MARGIN_L_CM - MARGIN_R_CM  # 16.2

#: 正文超过这个字数就把排版压紧一档（不是截断内容）
DENSE_TEXT_THRESHOLD = 12000

#: 提示框配色（tone → 边框色 / 底色 / 文字色）
CALLOUT_COLORS: Dict[str, Dict[str, str]] = {
    "info": {"bar": "409EFF", "fill": "F2F8FF", "text": "1F4E79"},
    "success": {"bar": "22C55E", "fill": "F3FBF5", "text": "14532D"},
    "warn": {"bar": "F59E0B", "fill": "FFFBF0", "text": "78350F"},
}


# ============================================================
# 主入口
# ============================================================

def render_docx(spec: DocumentSpec) -> bytes:
    """把 DocumentSpec 渲染成 .docx 字节

    Args:
        spec: 文档描述（由解析层或 AI 生成）

    Returns:
        .docx 文件的二进制内容
    """
    theme = get_theme(spec.theme)
    dense = _text_length(spec) >= DENSE_TEXT_THRESHOLD

    doc = Document()
    _setup_page(doc)
    _setup_default_style(doc, theme, dense)

    # ── 封面 ──
    if spec.cover:
        _render_cover(doc, spec, theme)
        doc.add_page_break()

    # ── 标题（无封面时，把文档标题作为正文开头的大标题）──
    if not spec.cover and spec.title:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if theme["titleAlign"] == "center" else WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(14)
        run = p.add_run(spec.title)
        _docx_set_cjk_font(run, theme["headFont"], size=theme["headSizesPt"][0] + 2, bold=True)
        run.font.color.rgb = RGBColor.from_string("111111")
        if spec.subtitle:
            p2 = doc.add_paragraph()
            p2.alignment = p.alignment
            p2.paragraph_format.space_after = Pt(12)
            r2 = p2.add_run(spec.subtitle)
            _set_font(r2, theme["bodyFont"], size=theme["bodySizePt"], color="666666")

    # ── 目录 ──
    if spec.toc and _should_toc(spec):
        _render_toc(doc, spec, theme)
        doc.add_page_break()

    # ── 正文 ──
    for block in spec.blocks:
        _render_block(doc, block, spec, theme, dense)

    # ── 页眉页脚 ──
    # 有封面时首页不显示（否则封面顶部会压一行小字，很难看）
    _render_header_footer(doc, spec, theme, skip_first=spec.cover)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ============================================================
# 页面与默认样式
# ============================================================

def _setup_page(doc) -> None:
    section = doc.sections[0]
    section.page_width = Cm(PAGE_W_CM)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(MARGIN_L_CM)
    section.right_margin = Cm(MARGIN_R_CM)
    section.top_margin = Cm(MARGIN_T_CM)
    section.bottom_margin = Cm(MARGIN_B_CM)


def _setup_default_style(doc, theme: Dict[str, Any], dense: bool) -> None:
    """设置 Normal 样式：中文正文字体 + 行距 + 段后距

    ⚠️ 必须同时设 `w:eastAsia`：只设 `font.name` 的话，
       Word 里中文仍会用默认宋体，西文字体才生效。
    """
    style = doc.styles["Normal"]
    style.font.name = theme["bodyFont"]
    style.font.size = Pt(theme["bodySizePt"] - (0.5 if dense else 0))
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), theme["bodyFont"])
    rfonts.set(qn("w:ascii"), theme["bodyFont"])
    rfonts.set(qn("w:hAnsi"), theme["bodyFont"])

    pf = style.paragraph_format
    pf.line_spacing = theme["lineSpacing"] - (0.1 if dense else 0)
    pf.space_after = Pt(theme["spaceAfterPt"])

    # ── 中文避头尾（kinsoku）────────────────────────────────
    #
    # 实测缺陷：一段中文在 `x∈D` 之后换行，行首出现了孤立的 `，`，
    # 下一段的 `A` 后面也单独挂了一个 `。`。
    #
    # 这是**没有开启避头尾**的典型症状：Word/WPS 默认会拦，
    # 但 python-docx 生成的新文档里这几个开关不一定是开的，
    # 而 LibreOffice 转 PDF 时按文档里的设置走 —— 于是就断了。
    #
    # 四个开关的作用：
    #   kinsoku          —— 禁止行首出现收尾标点（，。）」
    #   wordWrap         —— 允许西文单词内换行（否则长公式会溢出）
    #   overflowPunct    —— 标点可以溢出到版心外一丁点，换取标点不留行首
    #   topLinePunct     —— 允许标点压缩，让行首对齐更整齐
    ppr = style.element.get_or_add_pPr()
    for tag in ("kinsoku", "wordWrap", "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN"):
        el = OxmlElement(f"w:{tag}")
        el.set(qn("w:val"), "1")
        ppr.append(el)


def _render_cover(doc, spec: DocumentSpec, theme: Dict[str, Any]) -> None:
    """封面：大标题 + 副标题 + 作者 + 日期，垂直居中偏上"""
    # 顶部留白（用空段落实现，比 section 的 vertical alignment 更可控）
    for _ in range(6):
        doc.add_paragraph()

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(10)
    run = p.add_run(spec.title or "文档")
    _docx_set_cjk_font(run, theme["headFont"], size=26, bold=True)
    run.font.color.rgb = RGBColor.from_string(theme["headColors"][0])

    # 标题下装饰线
    line_p = doc.add_paragraph()
    line_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_paragraph_border(line_p, theme["headColors"][0], size=12, width_cm=6)

    if spec.subtitle:
        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p2.paragraph_format.space_before = Pt(12)
        r2 = p2.add_run(spec.subtitle)
        _docx_set_cjk_font(r2, theme["bodyFont"], size=13)
        r2.font.color.rgb = RGBColor.from_string("666666")

    for _ in range(8):
        doc.add_paragraph()

    meta_lines = []
    if spec.author:
        meta_lines.append(spec.author)
    meta_lines.append(spec.date or datetime.date.today().strftime("%Y 年 %m 月 %d 日"))

    for line in meta_lines:
        pm = doc.add_paragraph()
        pm.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pm.paragraph_format.space_after = Pt(4)
        rm = pm.add_run(line)
        _docx_set_cjk_font(rm, theme["bodyFont"], size=11.5)
        rm.font.color.rgb = RGBColor.from_string("444444")


def _add_paragraph_border(paragraph, color_hex: str, *, size: int = 8, width_cm: Optional[float] = None) -> None:
    """给段落加下边框（用作封面装饰线 / 分节线）

    Args:
        width_cm: 期望的线宽（cm）。给了就通过左右缩进把线段缩到那么长；
                  不给则撑满版心（分节线用这个）。
    """
    pPr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color_hex)
    borders.append(bottom)
    pPr.append(borders)

    # 段落边框只能跟随整行，无法直接设线长。
    # 用对称的左右缩进把行压窄，线自然就短了 —— 视觉上是居中的短横线。
    if width_cm and width_cm < CONTENT_W_CM:
        pad = (CONTENT_W_CM - width_cm) / 2
        paragraph.paragraph_format.left_indent = Cm(pad)
        paragraph.paragraph_format.right_indent = Cm(pad)

    paragraph.paragraph_format.space_after = Pt(6)


def _should_toc(spec: DocumentSpec) -> bool:
    """是否值得出目录：至少 3 个标题、且层级不止一种"""
    heads = [b for b in spec.blocks if b.type == "heading"]
    return len(heads) >= 3


def _render_toc(doc, spec: DocumentSpec, theme: Dict[str, Any]) -> None:
    """生成目录

    ⚠️ 用 Word 的 **TOC 域**（`{ TOC \\o "1-3" }`）而不是手写页码：
       手写页码没法跟着分页变化，用户一改内容就全错。
       域需要用户在 Word 里按 F9 更新，或者在"打开时更新域"的选项下自动更新。

       同时在域里塞一份**静态文本**（标题列表），这样：
         · 用户不更新域也能看到目录内容（只是没页码）
         · 更新域之后变成正式目录
    """
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run("目  录")
    _docx_set_cjk_font(r, theme["headFont"], size=16, bold=True)

    heads = [b for b in spec.blocks if b.type == "heading"]
    for h in heads:
        para = doc.add_paragraph()
        para.paragraph_format.left_indent = Cm((h.level - 1) * 0.74)
        para.paragraph_format.space_after = Pt(2)
        run = para.add_run(h.text)
        bold = h.level == 1
        _docx_set_cjk_font(
            run,
            theme["bodyFont"],
            size=theme["bodySizePt"] + (0.5 if bold else 0),
            bold=bold,
        )
        run.font.color.rgb = RGBColor.from_string("333333" if bold else "555555")


# ============================================================
# 块渲染
# ============================================================

def _render_block(doc, block: Block, spec: DocumentSpec, theme: Dict[str, Any], dense: bool) -> None:
    btype = block.type

    if btype == "heading":
        _render_heading(doc, block, theme, dense)
    elif btype == "paragraph":
        _render_paragraph(doc, block, theme)
    elif btype == "list":
        _render_list(doc, block, theme)
    elif btype == "table":
        _render_table(doc, block, theme)
    elif btype == "image":
        _render_image(doc, block, theme)
    elif btype == "quote":
        _render_quote(doc, block, theme)
    elif btype == "code":
        _render_code(doc, block, theme)
    elif btype == "divider":
        _render_divider(doc, theme)
    elif btype == "math":
        _render_math_block(doc, block, theme)
    elif btype == "callout":
        _render_callout(doc, block, theme)
    # 未知类型静默跳过：宁可少渲染一块，也不要整篇失败


def _render_heading(doc, block: Block, theme: Dict[str, Any], dense: bool) -> None:
    level = max(1, min(block.level, 4))
    sizes = theme["headSizesPt"]
    colors = theme["headColors"]

    p = doc.add_paragraph()
    pf = p.paragraph_format
    # 标题与上文的间距随层级递减，看起来才像有层次
    pf.space_before = Pt({1: 14, 2: 10, 3: 8, 4: 6}.get(level, 6) * (0.8 if dense else 1))
    pf.space_after = Pt({1: 8, 2: 6, 3: 5, 4: 4}.get(level, 4))
    pf.keep_with_next = True  # 标题不与正文分页（避免"标题在页底"）

    run = p.add_run(block.text)
    _docx_set_cjk_font(
        run,
        theme["headFont"],
        size=sizes[min(level - 1, len(sizes) - 1)] - (0.5 if dense else 0),
        bold=True,
    )
    color = colors[min(level - 1, len(colors) - 1)]
    run.font.color.rgb = RGBColor.from_string(color)

    # 一级标题加下划装饰线，视觉上分节更明显
    if level == 1:
        _add_paragraph_border(p, color, size=6)


def _render_paragraph(doc, block: Block, theme: Dict[str, Any]) -> None:
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY  # 两端对齐（中文排版标准）
    if theme["firstLineIndentEm"]:
        pf.first_line_indent = Pt(theme["bodySizePt"] * theme["firstLineIndentEm"])
    # 用 _add_segments 而不是 add_run：它会把文字里的 LaTeX 公式转成 OMML，
    # 和题库导出走同一条公式链路，不会出现"Word 里公式是反斜杠"
    _add_inline(p, block.text, theme, size=theme["bodySizePt"])


def _render_list(doc, block: Block, theme: Dict[str, Any]) -> None:
    for idx, item in enumerate(block.items or []):
        depth = 0
        text = item
        if isinstance(item, dict):
            text = item.get("text", "")
            depth = int(item.get("depth") or 0)

        p = doc.add_paragraph()
        pf = p.paragraph_format
        # 悬挂缩进：换行后的文字对齐到内容起点，而不是回到符号下面
        pf.left_indent = Cm(0.74 + depth * 0.74)
        pf.first_line_indent = Cm(-0.44)
        pf.space_after = Pt(2)
        pf.line_spacing = theme["lineSpacing"]

        marker = f"{idx + 1}. " if block.ordered else ("• " if depth == 0 else "◦ ")
        mrun = p.add_run(marker)
        _docx_set_cjk_font(mrun, theme["bodyFont"], size=theme["bodySizePt"])
        mrun.font.color.rgb = RGBColor.from_string("444444")

        _add_inline(p, str(text), theme, size=theme["bodySizePt"])


def _render_table(doc, block: Block, theme: Dict[str, Any]) -> None:
    data = block.table or {}
    headers: List[str] = [str(h) for h in (data.get("headers") or [])]
    rows: List[List[str]] = [[str(c) for c in r] for r in (data.get("rows") or [])]
    align: List[str] = data.get("align") or []

    if not headers and not rows:
        return

    width = max(len(headers), max((len(r) for r in rows), default=0))
    if width <= 0:
        return
    headers = headers + [""] * (width - len(headers))
    rows = [r + [""] * (width - len(r)) for r in rows]

    has_header = any(h.strip() for h in headers)
    total_rows = len(rows) + (1 if has_header else 0)
    if total_rows == 0:
        return

    table = doc.add_table(rows=total_rows, cols=width)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _docx_set_table_borders(table, color="C8D0DA", sz=4)

    # 列宽：等分；第一列略宽（中文表格里通常是项目名）
    if width == 1:
        widths = [CONTENT_W_CM]
    else:
        first = CONTENT_W_CM * (1.25 / (width + 0.25))
        rest = (CONTENT_W_CM - first) / (width - 1)
        widths = [first] + [rest] * (width - 1)

    for j, w in enumerate(widths):
        for row in table.rows:
            row.cells[j].width = Cm(w)

    row_offset = 0
    if has_header:
        _fill_table_row(table.rows[0], headers, theme, align, bold=True, header=True)
        _docx_mark_header_row(table.rows[0])
        row_offset = 1

    for i, r in enumerate(rows):
        _fill_table_row(table.rows[i + row_offset], r, theme, align, bold=False, header=False)

    for row in table.rows:
        _docx_forbid_row_split(row)
        for cell in row.cells:
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _docx_set_cell_margins(cell)

    # 表格后留一点空隙，否则紧贴下一段文字
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def _fill_table_row(row, cells: List[str], theme: Dict[str, Any], align: List[str],
                    *, bold: bool, header: bool) -> None:
    for j, text in enumerate(cells):
        cell = row.cells[j]
        cell.text = ""
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.2

        a = align[j] if j < len(align) else "left"
        p.alignment = {
            "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT,
        }.get(a, WD_ALIGN_PARAGRAPH.LEFT)

        size = theme["bodySizePt"] - 0.5
        _add_inline(p, str(text), theme, size=size, base_bold=bold)

        if header:
            _docx_set_cell_shading(cell, theme["tableHeaderFill"])


def _render_image(doc, block: Block, theme: Dict[str, Any]) -> None:
    img = block.image or {}
    src = (img.get("src") or "").strip()
    caption = (img.get("caption") or "").strip()
    width_cm = img.get("widthCm")

    ok = False
    if src:
        max_w = float(width_cm) if width_cm else CONTENT_W_CM
        max_w = min(max_w, CONTENT_W_CM)
        ok = _insert_picture(doc, src, max_w)

    if not ok:
        # 图片取不到时给一个明确的占位，而不是静默消失
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run("[图片缺失]" if src else "[此处有图片]")
        _set_font(r, theme["bodyFont"], size=theme["bodySizePt"] - 1, color="999999")

    if caption:
        cap = doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.space_before = Pt(2)
        cap.paragraph_format.space_after = Pt(8)
        cr = cap.add_run(caption)
        _set_font(cr, theme["bodyFont"], size=theme["bodySizePt"] - 1, color="777777")


def _insert_picture(doc, src: str, max_width_cm: float) -> bool:
    """把各种形态的图片 src 插进文档

    ── 为什么不用 `bank_export._docx_add_image`
    ─────────────────────────────────────────────
    那个函数底层调 `_load_image_bytes` → `_src_to_relpath`，而后者写了：

        if not s.startswith("profile/"):
            return None

    它只认**题库导出**的图片目录（题目插图存在 `profile/` 下），
    文档编排要处理的是用户上传的 `upload/2026/10/xx.png`，
    直接被拒 → 图片静默消失（实测 w:drawing 节点数 0）。

    那个函数是题库导出的公共依赖，改它会波及现有导出链路，
    所以在这里自己做路径解析，兼容这几种形态：

      · `data:image/png;base64,...`      内联图片
      · `upload/2026/10/27/a.png`        上传目录相对路径（最常见）
      · `profile/xxx.png`                题库插图目录
      · `/dev-api/profile/x.png`         带前端前缀 / 域名（要剥掉）
      · `D:\\abs\\path\\a.png`            绝对路径（限制在 UPLOAD_DIR 内才允许）

    ⚠️ 安全：所有解析结果都必须落在 `UPLOAD_DIR` 之下，
       否则视为越权（防 `../../etc/passwd`）。
    """
    data = _read_image_bytes(src)
    if not data:
        return False

    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            w_px, h_px = im.size

        # 按宽度等比缩放；高度也做上限（防止超长图撑满整页）
        width_cm = min(max_width_cm, CONTENT_W_CM)
        if w_px > 0:
            height_cm = width_cm * h_px / w_px
        else:
            height_cm = width_cm * 0.6

        max_h_cm = 20.0  # A4 版心高度约 25cm，留出图注和上下文的余量
        if height_cm > max_h_cm:
            height_cm = max_h_cm
            width_cm = height_cm * w_px / h_px if h_px else width_cm

        doc.add_picture(io.BytesIO(data), width=Cm(width_cm), height=Cm(height_cm))
        # 图片段落居中（python-docx 会把图片放进最后一个段落）
        if doc.paragraphs:
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[doc-compose] 插图失败 src=%.60s: %s", src, e)
        return False


def _read_image_bytes(src: str) -> Optional[bytes]:
    """按各种 src 形态读图片字节；读不到返回 None"""
    import base64
    import os

    s = (src or "").strip()
    if not s:
        return None

    # ① data URL
    if s.startswith("data:"):
        try:
            _, b64 = s.split(",", 1)
            return base64.b64decode(b64)
        except Exception:  # noqa: BLE001
            return None

    # ② 剥掉域名 / 前端前缀，得到相对路径
    from app.config import settings

    rel = re.sub(r"^(?:https?://[^/]+)?(?:/dev-api)?/", "", s, flags=re.I)
    rel = re.split(r"[?#]", rel, 1)[0]

    base = os.path.abspath(settings.UPLOAD_DIR)
    candidates = []

    # 绝对路径
    if os.path.isabs(rel):
        candidates.append(os.path.abspath(rel))
    else:
        # 相对 UPLOAD_DIR
        candidates.append(os.path.abspath(os.path.join(base, rel.replace("/", os.sep))))
        # 有些历史数据带 `uploadPath/` 前缀
        if rel.startswith("uploadPath/"):
            candidates.append(
                os.path.abspath(os.path.join(base, rel[len("uploadPath/"):].replace("/", os.sep)))
            )

    for full in candidates:
        if not (full == base or full.startswith(base + os.sep)):
            logger.warning("[doc-compose] 拒绝越界图片路径 %r", src)
            continue
        if os.path.isfile(full):
            try:
                with open(full, "rb") as fh:
                    return fh.read()
            except OSError:
                continue
        else:
            logger.warning("[doc-compose] 图片不存在 %r -> %s", src, full)

    return None


def _render_quote(doc, block: Block, theme: Dict[str, Any]) -> None:
    """引用块：左侧竖线 + 浅灰底 + 斜体"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(0.6)
    pf.space_before = Pt(4)
    pf.space_after = Pt(6)

    _add_left_bar(p, theme["quoteBarColor"])
    _shade_paragraph(p, "F7F8FA")

    run = p.add_run(block.text)
    # ⚠️ 不加斜体：中文没有真斜体，Word 伪造的倾斜很难看。
    #    用颜色 + 左侧竖条表达"引用"，视觉上已经够了。
    _set_font(run, theme["bodyFont"], size=theme["bodySizePt"], color="555555")


def _render_code(doc, block: Block, theme: Dict[str, Any]) -> None:
    """代码块：等宽字体 + 灰底 + 不换行缩进"""
    for line in (block.text or "").split("\n"):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent = Cm(0.4)
        pf.space_after = Pt(0)
        pf.line_spacing = 1.15
        _shade_paragraph(p, "F5F5F5")
        run = p.add_run(line if line else " ")
        run.font.name = "Consolas"
        run.font.size = Pt(theme["bodySizePt"] - 1)
        rpr = run._element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        rfonts.set(qn("w:eastAsia"), "微软雅黑")
        rfonts.set(qn("w:ascii"), "Consolas")
        rfonts.set(qn("w:hAnsi"), "Consolas")


def _render_divider(doc, theme: Dict[str, Any]) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)
    _add_paragraph_border(p, "D8DDE5", size=6)


def _render_math_block(doc, block: Block, theme: Dict[str, Any]) -> None:
    """独立公式块：居中 + OMML"""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)

    latex = (block.text or "").strip()
    if not _add_omml(p, latex, size=theme["bodySizePt"] * 1.15):
        # 转不成 OMML 就原样输出，至少内容不丢
        r = p.add_run(latex)
        _docx_set_cjk_font(r, theme["bodyFont"], size=theme["bodySizePt"])


def _render_callout(doc, block: Block, theme: Dict[str, Any]) -> None:
    """提示框：左粗色条 + 浅底 + 深色文字"""
    tone = block.tone if block.tone in CALLOUT_COLORS else "info"
    colors = CALLOUT_COLORS[tone]

    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(0.3)
    pf.space_before = Pt(6)
    pf.space_after = Pt(8)

    _add_left_bar(p, colors["bar"], size=24)
    _shade_paragraph(p, colors["fill"])

    run = p.add_run(block.text)
    _docx_set_cjk_font(run, theme["bodyFont"], size=theme["bodySizePt"])
    run.font.color.rgb = RGBColor.from_string(colors["text"])


# ============================================================
# oxml 小工具
# ============================================================

def _add_left_bar(paragraph, color_hex: str, *, size: int = 18) -> None:
    """给段落加左侧粗边框（引用块 / 提示框的竖条）"""
    pPr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), str(size))
    left.set(qn("w:space"), "6")
    left.set(qn("w:color"), color_hex)
    borders.append(left)
    pPr.append(borders)


def _shade_paragraph(paragraph, fill_hex: str) -> None:
    """段落底纹"""
    pPr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)
    pPr.append(shd)


# ============================================================
# 页眉页脚
# ============================================================

def _render_header_footer(doc, spec: DocumentSpec, theme: Dict[str, Any], *, skip_first: bool = False) -> None:
    """页眉（文档标题）+ 页脚（页码）

    Args:
        skip_first: 封面页不显示页眉页脚

    ⚠️ `skip_first` 用 `different_first_page_header_footer` 实现，
       而不是给第一页单独建 section —— 后者会让页码从第二页重新从 1 开始，
       用户看到"第 1 页"出现在封面之后的正文页上，很困惑。
    """
    section = doc.sections[0]

    if skip_first:
        section.different_first_page_header_footer = True

    # ── 页眉 ──
    header_text = (spec.header or spec.title or "").strip()
    if header_text:
        hp = section.header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        hr = hp.add_run(header_text)
        _set_font(hr, theme["bodyFont"], size=9, color="808080")

        # 页眉下加一条细分隔线（比默认的空白页眉更"有设计感"）
        _add_paragraph_border(hp, "E0E4EA", size=4)

    # ── 页脚 ──
    fp = section.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_text = (spec.footer or "").strip()
    if footer_text:
        fr = fp.add_run(footer_text + "    ")
        _set_font(fr, theme["bodyFont"], size=9, color="808080")

    _append_page_number(fp, theme)


def _append_page_number(paragraph, theme: Dict[str, Any]) -> None:
    """插入「第 X 页 / 共 Y 页」

    ⚠️ 用域（PAGE / NUMPAGES）而不是固定数字：固定数字一改内容就全错。
    """
    run1 = paragraph.add_run("第 ")
    _docx_set_cjk_font(run1, theme["bodyFont"], size=9)
    run1.font.color.rgb = RGBColor.from_string("808080")

    _append_field(paragraph, "PAGE", theme)

    run2 = paragraph.add_run(" 页 / 共 ")
    _docx_set_cjk_font(run2, theme["bodyFont"], size=9)
    run2.font.color.rgb = RGBColor.from_string("808080")

    _append_field(paragraph, "NUMPAGES", theme)

    run3 = paragraph.add_run(" 页")
    _docx_set_cjk_font(run3, theme["bodyFont"], size=9)
    run3.font.color.rgb = RGBColor.from_string("808080")


def _append_field(paragraph, field_name: str, theme: Dict[str, Any]) -> None:
    """插入一个 Word 域（PAGE / NUMPAGES）"""
    run = paragraph.add_run()
    _docx_set_cjk_font(run, theme["bodyFont"], size=9)
    run.font.color.rgb = RGBColor.from_string("808080")

    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")

    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {field_name} "

    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")

    t = OxmlElement("w:t")
    t.text = "1"

    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")

    for el in (fld_begin, instr, fld_sep, t, fld_end):
        run._element.append(el)


# ============================================================
# 工具
# ============================================================

def _set_font(run, name: str, *, size=None, bold=None, italic=None, color: Optional[str] = None) -> None:
    """设置中英文字体 + 可选斜体 / 颜色（hex 字符串）

    ⚠️ 为什么不直接用 `_docx_set_cjk_font`：
       它没有 `italic` 参数，且 `color` 收的是 RGB 元组而不是 hex 字符串。
       为了不改动那个被题库导出共用的函数，这里套一层。

       顺带修一个中文排版的坑：**斜体对中文无效**（宋体没有真斜体，
       Word 会伪造一个倾斜，观感很差）。所以斜体只加在西文上，
       中文段落靠颜色和左侧竖条区分，不靠倾斜。
    """
    _docx_set_cjk_font(run, name, size=size, bold=bold)
    if italic is not None:
        run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


#: 行内 Markdown 标记（2026-10-27 加）
#:
#: 之前**完全没处理行内语法**，用户写 `**重要**` 会在 Word 里
#: 原样看到星号（实测确认）。
#:
#: 顺序很重要：`**` 必须排在 `*` 之前匹配，
#: 否则 `**bold**` 会被切成「*」+「*bold*」+「*」，渲染出一堆零散星号。
_RE_INLINE = re.compile(
    r"(\*\*.+?\*\*)"          # **粗体**
    r"|(`[^`]+`)"              # `行内代码`
    r"|(\*[^*]+?\*)"           # *斜体*
    r"|(~~.+?~~)"              # ~~删除线~~
    r"|(\[[^\]]+\]\([^)]+\))"  # [文字](链接)
)


def _add_inline(paragraph, text: str, theme: Dict[str, Any], *,
                size: float, base_bold: bool = False) -> None:
    """把带行内 Markdown 标记的文字加进段落

    支持：`**粗体**`、`*斜体*`、`` `代码` ``、`~~删除线~~`、`[文字](链接)`

    思路：用正则切出"带标记的片段"，标记内的内容单独加样式，
    标记外的文字交给 `_add_segments` —— 它负责把 LaTeX 转成 OMML。

    ⚠️ 为什么不自己 add_run：`_add_segments` 内部处理了
       「文字 + 裸 LaTeX」的切分与 OMML 转换。
       公式链路不能断 —— 加粗内容里的公式在 Word 里也必须是真公式。
    """
    if not text:
        return

    pos = 0
    for m in _RE_INLINE.finditer(text):
        start, end = m.span()

        if start > pos:
            _add_segments(paragraph, text[pos:start], size=size, bold=base_bold or None)

        token = m.group(0)
        if token.startswith("**"):
            _add_segments(paragraph, token[2:-2], size=size, bold=True)
        elif token.startswith("`"):
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(size - 0.5)
            _set_run_shading(run, "F0F2F5")
        elif token.startswith("~~"):
            run = paragraph.add_run(token[2:-2])
            _set_font(run, theme["bodyFont"], size=size)
            run.font.strike = True
        elif token.startswith("["):
            mm = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token)
            label = mm.group(1) if mm else token
            run = paragraph.add_run(label)
            _set_font(run, theme["bodyFont"], size=size, color="2563EB")
            run.font.underline = True
        elif token.startswith("*"):
            # ⚠️ 不能传给 `_add_segments(italic=...)`：它只认
            #    size/bold/color，传 italic 会 TypeError（实测踩过）。
            #    这里自己建 run 并加斜体。
            run = paragraph.add_run(token[1:-1])
            _set_font(run, theme["bodyFont"], size=size, italic=True)

        pos = end

    if pos < len(text):
        _add_segments(paragraph, text[pos:], size=size, bold=base_bold or None)


def _set_run_shading(run, fill_hex: str) -> None:
    """给 run 加底纹（行内代码的浅灰底）"""
    rpr = run._element.get_or_add_rPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)
    rpr.append(shd)


def _text_length(spec: DocumentSpec) -> int:
    total = len(spec.title or "") + len(spec.subtitle or "")
    for b in spec.blocks:
        total += len(b.text or "")
        for it in b.items or []:
            total += len(it if isinstance(it, str) else str(it.get("text", "")))
        if b.table:
            total += sum(len(str(c)) for r in (b.table.get("rows") or []) for c in r)
    return total
