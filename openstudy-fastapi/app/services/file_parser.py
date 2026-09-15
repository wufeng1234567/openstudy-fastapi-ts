"""
文件解析服务 - 支持 TXT/MD/DOCX/PDF
- DOCX: 使用 python-docx 提取段落+图片+表格,OMML 公式转 LaTeX
- PDF: 使用 pypdf 提取文本
- TXT/MD: 直接读取
返回结构化块: {textContent, blocks, images, totalTextLength}
"""

import base64
import io
import xml.etree.ElementTree as ET
from typing import Optional

# OMML / WordprocessingML 命名空间
_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

W_NS = _NS["w"]
M_NS = _NS["m"]


def _qn(ns: str, tag: str) -> str:
    """构造带命名空间的限定标签名 {ns}tag"""
    return f"{{{ns}}}{tag}"


# ============================================================
# OMML -> LaTeX 转换
# ============================================================
def _omml_to_latex(elem: ET.Element) -> str:
    """将 <m:oMath> 元素转换为 LaTeX 字符串(递归处理)。

    只实现常见结构:分数、根号、上下标、求和/积分、定界符、run。
    未识别元素回退为提取其纯文本。
    """
    return _convert_element(elem).strip()


def _convert_element(elem: ET.Element) -> str:
    """递归转换单个 OMML 元素"""
    tag = elem.tag
    # 去掉命名空间,只保留本地名
    if "}" in tag:
        tag = tag.split("}", 1)[1]

    if tag == "oMath":
        # 公式块:拼接所有子元素
        return "".join(_convert_element(child) for child in elem)

    if tag == "oMathPara":
        # 展示型公式块,内部含 oMath
        return "".join(_convert_element(child) for child in elem)

    if tag == "r":
        # run:取 <m:t> 文本
        return _run_text(elem)

    if tag == "t":
        return elem.text or ""

    if tag == "f":
        # 分数 \frac{num}{den}
        num = _find_child_local(elem, "num")
        den = _find_child_local(elem, "den")
        num_latex = _convert_element(num) if num is not None else ""
        den_latex = _convert_element(den) if den is not None else ""
        return f"\\frac{{{num_latex}}}{{{den_latex}}}"

    if tag == "rad":
        # 根号 \sqrt{content} 或 \sqrt[deg]{content}
        deg = _find_child_local(elem, "deg")
        e = _find_child_local(elem, "e")
        e_latex = _convert_element(e) if e is not None else ""
        if deg is not None and _has_content(deg):
            deg_latex = _convert_element(deg)
            return f"\\sqrt[{deg_latex}]{{{e_latex}}}"
        return f"\\sqrt{{{e_latex}}}"

    if tag == "sSup":
        # 上标 base^{sup}
        e = _find_child_local(elem, "e")
        sup = _find_child_local(elem, "sup")
        base = _convert_element(e) if e is not None else ""
        sup_latex = _convert_element(sup) if sup is not None else ""
        return f"{{{base}}}^{{{sup_latex}}}"

    if tag == "sSub":
        # 下标 base_{sub}
        e = _find_child_local(elem, "e")
        sub = _find_child_local(elem, "sub")
        base = _convert_element(e) if e is not None else ""
        sub_latex = _convert_element(sub) if sub is not None else ""
        return f"{{{base}}}_{{{sub_latex}}}"

    if tag == "sSubSup":
        # 上下标同时 base_{sub}^{sup}
        e = _find_child_local(elem, "e")
        sub = _find_child_local(elem, "sub")
        sup = _find_child_local(elem, "sup")
        base = _convert_element(e) if e is not None else ""
        sub_latex = _convert_element(sub) if sub is not None else ""
        sup_latex = _convert_element(sup) if sup is not None else ""
        return f"{{{base}}}_{{{sub_latex}}}^{{{sup_latex}}}"

    if tag == "nary":
        # n 元运算符(求和/积分等),通过 m:chr 属性判断符号
        chr_val = _get_nary_char(elem)
        sub = _find_child_local(elem, "sub")
        sup = _find_child_local(elem, "sup")
        e = _find_child_local(elem, "e")
        op = _nary_char_to_latex(chr_val)
        sub_latex = _convert_element(sub) if sub is not None and _has_content(sub) else ""
        sup_latex = _convert_element(sup) if sup is not None and _has_content(sup) else ""
        e_latex = _convert_element(e) if e is not None else ""
        result = op
        if sub_latex:
            result += f"_{{{sub_latex}}}"
        if sup_latex:
            result += f"^{{{sup_latex}}}"
        result += f" {{{e_latex}}}"
        return result

    if tag == "d":
        # 定界符 \left( content \right)
        e = _find_child_local(elem, "e")
        e_latex = _convert_element(e) if e is not None else ""
        beg = _get_delimiter(elem, "begChr", "(")
        end = _get_delimiter(elem, "endChr", ")")
        return f"\\left{beg} {e_latex} \\right{end}"

    if tag == "e" or tag == "num" or tag == "den" or tag == "deg" \
            or tag == "sub" or tag == "sup":
        # 容器元素:递归拼接子元素
        return "".join(_convert_element(child) for child in elem)

    if tag == "fPr" or tag == "radPr" or tag == "sSupPr" or tag == "sSubPr" \
            or tag == "sSubSupPr" or tag == "naryPr" or tag == "dPr" or tag == "rPr":
        # 属性节点:忽略
        return ""

    # 默认:递归拼接子元素
    return "".join(_convert_element(child) for child in elem)


def _run_text(elem: ET.Element) -> str:
    """提取 <m:r> 内 <m:t> 的文本"""
    texts = []
    for t in elem.iter(_qn(M_NS, "t")):
        if t.text:
            texts.append(t.text)
    return "".join(texts)


def _find_child_local(elem: ET.Element, local_name: str) -> Optional[ET.Element]:
    """查找直接子元素中本地名为 local_name 的第一个元素(任意命名空间)"""
    for child in elem:
        ctag = child.tag
        if "}" in ctag:
            ctag = ctag.split("}", 1)[1]
        if ctag == local_name:
            return child
    return None


def _has_content(elem: ET.Element) -> bool:
    """判断元素是否含有实际内容(文本或子元素)"""
    if (elem.text or "").strip():
        return True
    return len(list(elem)) > 0


def _get_nary_char(elem: ET.Element) -> str:
    """从 <m:nary> 的 <m:naryPr><m:chr m:val="..."/> 取运算符字符"""
    nary_pr = _find_child_local(elem, "naryPr")
    if nary_pr is None:
        return ""
    chr_elem = _find_child_local(nary_pr, "chr")
    if chr_elem is None:
        return ""
    return chr_elem.get(_qn(M_NS, "val"), "") or chr_elem.get("val", "") or ""


def _nary_char_to_latex(chr_val: str) -> str:
    """将 nary 运算符字符映射为 LaTeX 命令"""
    mapping = {
        "∑": "\\sum",
        "∫": "\\int",
        "∏": "\\prod",
        "∪": "\\bigcup",
        "∩": "\\bigcap",
        "∮": "\\oint",
        "∬": "\\iint",
        "∭": "\\iiint",
    }
    return mapping.get(chr_val, "\\sum")


def _get_delimiter(elem: ET.Element, attr_local: str, default: str) -> str:
    """从 <m:dPr> 取定界符字符(begChr/endChr)"""
    d_pr = _find_child_local(elem, "dPr")
    if d_pr is None:
        return default
    node = _find_child_local(d_pr, attr_local)
    if node is None:
        return default
    val = node.get(_qn(M_NS, "val"), "") or node.get("val", "")
    return val if val else default


# ============================================================
# DOCX 段落文本提取(含 OMML 公式内联)
# ============================================================
def _extract_paragraph_text(p_elem: ET.Element) -> str:
    """遍历 <w:p> 的子元素,拼接文本 run 与 OMML 公式。

    - <w:r><w:t> -> 纯文本
    - <m:oMath> / <m:oMathPara> -> $latex$
    """
    parts = []
    for child in p_elem:
        ctag = child.tag
        if "}" in ctag:
            ctag = ctag.split("}", 1)[1]

        if ctag == "r":
            # word run:取所有 <w:t> 文本
            for t in child.iter(_qn(W_NS, "t")):
                if t.text:
                    parts.append(t.text)
        elif ctag == "oMath":
            latex = _omml_to_latex(child)
            if latex:
                parts.append(f"${latex}$")
        elif ctag == "oMathPara":
            # 展示型公式,可能含多个 oMath
            for omath in child.iter(_qn(M_NS, "oMath")):
                latex = _omml_to_latex(omath)
                if latex:
                    parts.append(f"$${latex}$$")
        elif ctag == "hyperlink":
            # 超链接中的 run 文本
            for t in child.iter(_qn(W_NS, "t")):
                if t.text:
                    parts.append(t.text)
    return "".join(parts)


# ============================================================
# 主解析逻辑
# ============================================================
def parse_file(filename: str, content: bytes) -> dict:
    """主入口:根据文件扩展名分发解析。

    Args:
        filename: 文件名(用于判断扩展名)
        content: 文件二进制内容

    Returns:
        {textContent, blocks, images, totalTextLength, fileName}
    """
    if not filename:
        ext = ""
    else:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in ("txt", "md", "markdown"):
        result = _parse_txt(content)
    elif ext == "docx":
        result = _parse_docx(content)
    elif ext == "pdf":
        result = _parse_pdf(content)
    elif ext in ("doc",):
        # 老 doc 二进制格式 python-docx 不支持,返回提示
        result = {
            "textContent": "",
            "blocks": [],
            "images": [],
            "totalTextLength": 0,
            "error": "不支持老版 .doc 格式,请转换为 .docx",
        }
    else:
        # 未知类型:尝试按文本读取
        result = _parse_txt(content)

    result["fileName"] = filename
    return result


def _parse_txt(content: bytes) -> dict:
    """解析纯文本文件(TXT/MD)"""
    text = content.decode("utf-8", errors="ignore")
    blocks = []
    if text:
        blocks.append({"type": "text", "content": text, "orderIndex": 0})
    return {
        "textContent": text,
        "blocks": blocks,
        "images": [],
        "totalTextLength": len(text),
    }


def _parse_docx(content: bytes) -> dict:
    """解析 DOCX 文件:段落(含 OMML 公式)+ 图片 + 表格"""
    from docx import Document
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    doc = Document(io.BytesIO(content))

    blocks = []
    images = []
    order_index = 0
    text_parts = []

    # --- 提取图片关系映射(rId -> blob) ---
    image_blobs = {}  # rId -> (blob, content_type, ext)
    try:
        for rel in doc.part.rels.values():
            if rel.reltype == RT.IMAGE:
                try:
                    image_part = rel.target_part
                    blob = image_part.blob
                    content_type = image_part.content_type or "image/png"
                    ext = content_type.split("/", 1)[-1].split("+", 1)[0]
                    image_blobs[rel.rId] = (blob, content_type, ext)
                except Exception:
                    pass
    except Exception:
        pass

    # --- 遍历文档 body 的子元素,保持段落/表格/图片顺序 ---
    # 使用底层 XML 以便同时处理 OMML 公式与表格
    body = doc.element.body

    def _add_text_block(text: str):
        nonlocal order_index
        text = (text or "").strip()
        if text:
            blocks.append({
                "type": "text",
                "content": text,
                "orderIndex": order_index,
            })
            text_parts.append(text)
            order_index += 1

    def _add_image_block(blob: bytes, content_type: str, ext: str):
        nonlocal order_index
        if not blob:
            return
        b64 = base64.b64encode(blob).decode("ascii")
        data_url = f"data:{content_type};base64,{b64}"
        image_name = f"image{order_index + 1}.{ext}"
        blocks.append({
            "type": "image",
            "content": "",
            "orderIndex": order_index,
            "imageUrl": data_url,
            "imageName": image_name,
        })
        images.append({
            "orderIndex": order_index,
            "imageUrl": data_url,
            "imageName": image_name,
        })
        order_index += 1

    # 遍历 body 直接子元素
    for child in body:
        ctag = child.tag
        if "}" in ctag:
            ctag = ctag.split("}", 1)[1]

        if ctag == "p":
            # 段落:提取文本(含公式)+ 段落内图片
            text = _extract_paragraph_text(child)
            # 检测段落内的图片(通过 a:blip 引用)
            for blip in child.iter(_qn(_NS["a"], "blip")):
                embed = blip.get(_qn(_NS["r"], "embed"))
                if embed and embed in image_blobs:
                    blob, ctype, ext = image_blobs[embed]
                    _add_image_block(blob, ctype, ext)
            if text.strip():
                _add_text_block(text)

        elif ctag == "tbl":
            # 表格:转为文本块(行列用 | 分隔)
            try:
                table_obj = _find_table_by_element(doc, child)
                if table_obj is not None:
                    table_text = _table_to_text(table_obj)
                    _add_text_block(table_text)
                else:
                    # 兜底:提取表格内所有文本
                    cells = []
                    for t in child.iter(_qn(W_NS, "t")):
                        if t.text:
                            cells.append(t.text)
                    _add_text_block(" | ".join(cells))
            except Exception:
                cells = []
                for t in child.iter(_qn(W_NS, "t")):
                    if t.text:
                        cells.append(t.text)
                _add_text_block(" | ".join(cells))

    text_content = "\n".join(text_parts)
    return {
        "textContent": text_content,
        "blocks": blocks,
        "images": images,
        "totalTextLength": len(text_content),
    }


def _find_table_by_element(doc, tbl_elem):
    """通过底层 <w:tbl> 元素找到对应的 python-docx Table 对象"""
    try:
        from docx.table import Table
        return Table(tbl_elem, doc.element.body)
    except Exception:
        return None


def _table_to_text(table) -> str:
    """将表格转为纯文本(每行单元格用 | 分隔,行间换行)"""
    rows = []
    for row in table.rows:
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        rows.append(" | ".join(cells))
    return "\n".join(rows)


def _parse_pdf(content: bytes) -> dict:
    """解析 PDF 文件:仅提取文本(不支持图片)"""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    text_parts = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        if page_text:
            text_parts.append(page_text)

    text_content = "\n".join(text_parts)
    blocks = []
    if text_content:
        blocks.append({"type": "text", "content": text_content, "orderIndex": 0})
    return {
        "textContent": text_content,
        "blocks": blocks,
        "images": [],
        "totalTextLength": len(text_content),
    }
