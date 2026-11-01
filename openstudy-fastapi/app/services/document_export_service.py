"""资料正文的二次编辑导出：Markdown / Word。"""

from __future__ import annotations

import base64
import io
import mimetypes
import os
import re
from typing import Any, Dict, Tuple
from urllib.parse import quote

from docx import Document
from docx.shared import Inches, Pt

from app.config import settings


def _safe_image_path(url: str) -> str | None:
    """把 `/profile/...` 图片地址解析到 UPLOAD_DIR 下的真实文件。"""
    raw = str(url or "").strip()
    if not raw or raw.startswith("data:") or raw.startswith("http://") or raw.startswith("https://"):
        return None
    if raw.startswith("/profile/"):
        rel = raw[len("/profile/"):]
    elif raw.startswith("profile/"):
        rel = raw[len("profile/"):]
    elif raw.startswith("/dev-api/profile/"):
        rel = raw[len("/dev-api/profile/"):]
    else:
        rel = raw.lstrip("/")
    base = os.path.abspath(settings.UPLOAD_DIR)
    full = os.path.abspath(os.path.join(base, rel))
    if not full.startswith(base + os.sep):
        return None
    return full if os.path.isfile(full) else None


def _make_docx(raw: str, image_map: Dict[str, Any], title: str) -> bytes:
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(11)
    # East Asian 字体在 python-docx 里要单独设置
    try:
        style._element.rPr.rFonts.set(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", "宋体"
        )
    except Exception:
        pass

    if title:
        doc.add_heading(title, level=0)

    lines = (raw or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        image_match = re.fullmatch(r"【图(\d+)】", stripped)
        if image_match:
            url = image_map.get(image_match.group(1)) or image_map.get(int(image_match.group(1)))  # type: ignore
            path = _safe_image_path(str(url or ""))
            if path:
                try:
                    doc.add_picture(path, width=Inches(5.8))
                except Exception:
                    doc.add_paragraph("[图片]")
            i += 1
            continue

        markdown_image = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if markdown_image:
            path = _safe_image_path(markdown_image.group(2))
            if path:
                try:
                    doc.add_picture(path, width=Inches(5.8))
                except Exception:
                    doc.add_paragraph("[图片]")
            i += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            doc.add_heading(heading.group(2).strip(), level=min(6, len(heading.group(1))))
            i += 1
            continue

        # Markdown 表格：连续以 | 开头的行
        if stripped.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|", lines[i + 1]):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            rows = []
            for idx, row in enumerate(table_lines):
                cells = [c.strip() for c in row.strip("|").split("|")]
                if idx == 1 and all(re.fullmatch(r":?-{2,}:?", c or "") for c in cells):
                    continue
                rows.append(cells)
            if rows:
                cols = max(len(r) for r in rows)
                table = doc.add_table(rows=len(rows), cols=cols)
                table.style = "Table Grid"
                for ri, row in enumerate(rows):
                    for ci in range(cols):
                        table.cell(ri, ci).text = row[ci] if ci < len(row) else ""
            continue

        bullet = re.match(r"^\s*[-*+]\s+(.+)$", stripped)
        if bullet:
            p = doc.add_paragraph(bullet.group(1), style="List Bullet")
            p.paragraph_format.space_after = Pt(2)
            i += 1
            continue

        numbered = re.match(r"^\s*\d+[.、]\s+(.+)$", stripped)
        if numbered:
            p = doc.add_paragraph(numbered.group(1), style="List Number")
            p.paragraph_format.space_after = Pt(2)
            i += 1
            continue

        # 去掉常见的 Markdown 强调符号，保留正文与公式文本
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", stripped)
        text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
        doc.add_paragraph(text)
        i += 1

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _markdown_image_url(url: str) -> str:
    """Markdown 使用 data URL，导出的单个 .md 文件拿到任何编辑器都能显示图片。"""
    raw = str(url or "").strip()
    if not raw or raw.startswith("data:") or raw.startswith("http://") or raw.startswith("https://"):
        return raw
    path = _safe_image_path(raw)
    if not path:
        return raw
    try:
        mime = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as fh:
            encoded = base64.b64encode(fh.read()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except Exception:
        return raw


def _markdown_with_image_links(raw: str, image_map: Dict[str, Any]) -> str:
    """把正文里的【图N】位置标记转成标准 Markdown 图片。

    Markdown 本身完全可以显示图片；之前导出直接返回 raw，才会出现
    “图1、图2”这种裸标记。这里用 image_map 补上真实图片地址；本地图片
    会内嵌为 data URL，保证单独下载的 .md 也能被常见 Markdown 编辑器渲染。
    """
    def replace(match: re.Match[str]) -> str:
        index = match.group(1)
        url = image_map.get(index)
        if not url:
            url = image_map.get(int(index)) if index.isdigit() else None  # type: ignore
        return f"![图{index}]({_markdown_image_url(str(url))})" if url else match.group(0)

    return re.sub(r"【图(\d+)】", replace, raw or "")


def export_document(
    file_name: str, raw: str, image_map: Dict[str, Any], fmt: str
) -> Tuple[bytes, str, str]:
    """返回（字节、文件名、media_type）。"""
    stem = os.path.splitext(file_name or "资料")[0] or "资料"
    if fmt == "docx":
        return (
            _make_docx(raw, image_map, stem),
            f"{stem}.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    return (
        _markdown_with_image_links(raw, image_map).encode("utf-8"),
        f"{stem}.md",
        "text/markdown; charset=utf-8",
    )


def content_disposition(filename: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(filename)}"
