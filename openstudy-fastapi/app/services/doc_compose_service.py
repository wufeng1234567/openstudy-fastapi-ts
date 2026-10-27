"""
文档编排引擎：服务入口

把「解析 → 渲染 → PDF」串起来，对外提供三个动作：

    compose_from_markdown(text, ...)   一段文字/混乱 Markdown → 文档
    compose_from_file(parsed, ...)     上传的 Word/PDF 解析结果 → 重排后的文档
    compose_from_spec(spec_dict, ...)  AI 直接给的结构化描述 → 文档

三者最终都落到 `render()`：

    DocumentSpec ──► .docx 字节
                 └─► .pdf 字节（走 docx → LibreOffice，与题库导出同一条路）

============================================================================
为什么 PDF 要绕一圈
============================================================================

项目里试过两条直出 PDF 的路，都不行：

  · reportlab 直接排版：中文字体、公式、表格样式全要自己实现，
    工作量翻几倍，且排出来和 Word 版本长得不一样
  · 浏览器打印（Edge `--print-to-pdf` / CDP `Page.printToPDF`）：实测 `Target crashed`

现在的做法是 DOCX → LibreOffice → PDF（`pdf_docx_service`）：
  · 排版只写一次，Word 和 PDF 天然一致
  · 表格边框、底纹、公式都能保住
  · 代价是依赖 LibreOffice（项目里已经装了 kit）

LibreOffice 不可用时**自动退回只出 DOCX**，并明确告诉用户原因 ——
不能因为一个可选组件缺失就让整个功能失败。
"""
from __future__ import annotations

import io
import logging
from typing import Any, Dict, Optional, Tuple

from app.services.doc_compose_model import DocumentSpec, get_theme
from app.services.doc_compose_parser import analyze, parse_markdown, parse_parsed_file
from app.services.doc_compose_renderer import render_docx

logger = logging.getLogger(__name__)


# ============================================================
# 对外入口
# ============================================================

def compose_from_markdown(
    text: str,
    *,
    title: str = "",
    theme: str = "clean",
    cover: bool = False,
    toc: bool = False,
    want_pdf: bool = False,
) -> Dict[str, Any]:
    """一段文字 / 混乱 Markdown → 排版好的文档

    Returns:
        {
          "docx": bytes,
          "pdf": bytes | None,
          "pdfError": str | None,     # PDF 生成失败的原因（不致命）
          "spec": dict,               # 结构化描述（可回存、可再渲染）
          "analysis": dict,           # 输入有多乱、修了什么
          "theme": str,
          "blockCount": int,
        }
    """
    diag = analyze(text or "")
    spec = parse_markdown(text or "", title=title, theme=theme, cover=cover, toc=toc)
    return _finish(spec, diag, want_pdf=want_pdf)


def compose_from_file(
    parsed: Dict[str, Any],
    *,
    title: str = "",
    theme: str = "clean",
    cover: bool = False,
    toc: bool = False,
    want_pdf: bool = False,
) -> Dict[str, Any]:
    """上传文件的解析结果 → 重排后的文档

    `parsed` 是 `file_parser.parse_file()` 的返回（含 blocks / images）。
    """
    spec = parse_parsed_file(parsed or {}, title=title, theme=theme, cover=cover, toc=toc)
    diag = {
        "issues": [],
        "issueCount": 0,
        "blocks": len(spec.blocks),
        "charCount": int((parsed or {}).get("totalTextLength") or 0),
        "detectedTitle": spec.title,
        "source": "file",
    }
    return _finish(spec, diag, want_pdf=want_pdf)


def compose_from_spec(
    spec_dict: Dict[str, Any],
    *,
    want_pdf: bool = False,
) -> Dict[str, Any]:
    """AI 直接给出的结构化描述 → 文档

    `spec_dict` 形状与 `DocumentSpec.to_dict()` 一致。
    这里做**结构校验 + 容错**：AI 生成的结构经常
    缺字段、类型不对、把 level 写成字符串，不能直接信。
    """
    spec = _coerce_spec(spec_dict or {})
    diag = {
        "issues": [],
        "issueCount": 0,
        "blocks": len(spec.blocks),
        "charCount": sum(len(b.text or "") for b in spec.blocks),
        "detectedTitle": spec.title,
        "source": "spec",
    }
    return _finish(spec, diag, want_pdf=want_pdf)


# ============================================================
# 内部
# ============================================================

def _finish(spec: DocumentSpec, diag: Dict[str, Any], *, want_pdf: bool) -> Dict[str, Any]:
    """渲染 DOCX（+ 可选 PDF），并汇总结果"""
    docx_bytes = render_docx(spec)

    pdf_bytes: Optional[bytes] = None
    pdf_error: Optional[str] = None
    if want_pdf:
        pdf_bytes, pdf_error = _to_pdf(docx_bytes)

    return {
        "docx": docx_bytes,
        "pdf": pdf_bytes,
        "pdfError": pdf_error,
        "spec": spec.to_dict(),
        "analysis": diag,
        "theme": spec.theme,
        "themeLabel": get_theme(spec.theme).get("label", spec.theme),
        "blockCount": len(spec.blocks),
        "headingLevels": spec.heading_levels(),
    }


def _to_pdf(docx_bytes: bytes) -> Tuple[Optional[bytes], Optional[str]]:
    """DOCX → PDF（LibreOffice）

    ⚠️ 失败**不抛异常**：PDF 是增强项，DOCX 已经可用。
       把原因返回给调用方，由它决定怎么提示用户。
    """
    try:
        from app.services import pdf_docx_service
    except Exception as e:  # pragma: no cover - import 层面就不该失败
        return None, f"PDF 组件不可用：{e}"

    if not pdf_docx_service.is_available():
        return None, "未检测到 LibreOffice 转换组件，已生成 Word 文件（可用 Word 另存为 PDF）"

    try:
        out = pdf_docx_service.docx_to_pdf(docx_bytes)
    except Exception as e:
        logger.warning("[doc-compose] docx→pdf 失败: %s", e)
        return None, f"PDF 转换失败：{e}"

    if not out:
        return None, "PDF 转换未返回内容（LibreOffice 可能超时）"
    return out, None


# ============================================================
# AI 输入的容错
# ============================================================

_ALLOWED_TYPES = {
    "heading", "paragraph", "list", "table", "image",
    "quote", "code", "divider", "math", "callout",
}


def _coerce_spec(raw: Dict[str, Any]) -> DocumentSpec:
    """把（可能不规范的）dict 强制转成 DocumentSpec

    AI 生成的结构常见问题（都在这里兜住）：
      · `level` 是 `"2"` 字符串而不是数字
      · `items` 是字符串而不是数组
      · 块类型拼错（`"text"` / `"p"` / `"para"`）
      · table 的 rows 长度不齐
      · 整段内容塞在 `content` 而不是 `text`
    """
    from app.services.doc_compose_model import Block

    blocks: list[Block] = []
    for rb in raw.get("blocks") or []:
        if not isinstance(rb, dict):
            continue

        btype = str(rb.get("type") or "").strip().lower()
        btype = _normalize_type(btype)
        if btype not in _ALLOWED_TYPES:
            # 认不出来就按段落处理：至少内容不丢
            btype = "paragraph"

        text = rb.get("text")
        if text is None:
            text = rb.get("content")
        if text is None:
            text = rb.get("value")
        text = "" if text is None else str(text)

        block = Block(type=btype, text=text)

        if btype == "heading":
            try:
                block.level = max(1, min(int(rb.get("level") or 1), 4))
            except (TypeError, ValueError):
                block.level = 1

        elif btype == "list":
            items = rb.get("items")
            if isinstance(items, str):
                # "a\nb\nc" → ["a","b","c"]
                items = [ln.strip() for ln in items.split("\n") if ln.strip()]
            elif not isinstance(items, list):
                items = []
            block.items = items
            block.ordered = bool(rb.get("ordered"))

        elif btype == "table":
            block.table = _coerce_table(rb.get("table") or rb)

        elif btype == "image":
            img = rb.get("image") if isinstance(rb.get("image"), dict) else rb
            block.image = {
                "src": str(img.get("src") or img.get("url") or ""),
                "caption": str(img.get("caption") or ""),
                "widthCm": img.get("widthCm"),
            }

        elif btype == "callout":
            tone = str(rb.get("tone") or "info").lower()
            block.tone = tone if tone in ("info", "success", "warn") else "info"

        blocks.append(block)

    return DocumentSpec(
        title=str(raw.get("title") or ""),
        subtitle=str(raw.get("subtitle") or ""),
        author=str(raw.get("author") or ""),
        date=str(raw.get("date") or ""),
        theme=str(raw.get("theme") or "clean"),
        cover=bool(raw.get("cover")),
        toc=bool(raw.get("toc")),
        header=str(raw.get("header") or ""),
        footer=str(raw.get("footer") or ""),
        blocks=blocks,
    )


def _normalize_type(t: str) -> str:
    """把各种别名归一到内部类型"""
    alias = {
        "h1": "heading", "h2": "heading", "h3": "heading", "h4": "heading",
        "title": "heading", "head": "heading",
        "text": "paragraph", "p": "paragraph", "para": "paragraph",
        "body": "paragraph", "content": "paragraph",
        "ul": "list", "ol": "list", "bullet": "list",
        "img": "image", "picture": "image", "figure": "image",
        "hr": "divider", "line": "divider", "separator": "divider",
        "formula": "math", "equation": "math",
        "note": "callout", "tip": "callout", "warning": "callout",
        "codeblock": "code", "pre": "code",
    }
    return alias.get(t, t)


def _coerce_table(raw: Any) -> Dict[str, Any]:
    """表格字段容错：补齐列数、转字符串、修正 align"""
    if not isinstance(raw, dict):
        return {"headers": [], "rows": [], "align": []}

    headers = raw.get("headers") or raw.get("columns") or []
    if not isinstance(headers, list):
        headers = []
    headers = [str(h) for h in headers]

    rows_raw = raw.get("rows") or []
    rows: list[list[str]] = []
    if isinstance(rows_raw, list):
        for r in rows_raw:
            if isinstance(r, (list, tuple)):
                rows.append([str(c) for c in r])
            elif isinstance(r, dict):
                # [{"a": 1, "b": 2}] → 按 headers 顺序取值
                rows.append([str(r.get(h, "")) for h in headers])
            else:
                rows.append([str(r)])

    width = max(len(headers), max((len(r) for r in rows), default=0))
    if width == 0:
        return {"headers": [], "rows": [], "align": []}

    headers = headers + [""] * (width - len(headers))
    rows = [r + [""] * (width - len(r)) for r in rows]

    align = raw.get("align") or []
    if not isinstance(align, list) or len(align) != width:
        align = ["left"] * width

    return {"headers": headers, "rows": rows, "align": align}
