"""
MathML → OMML（Office Math Markup Language）转换器

为什么要这一步
=============
Word 里的**原生公式**是 OMML（`<m:oMath>` 内嵌在 `w:p` 里），不是 MathML。
把 MathML 直接写进 .docx，Word/WPS 都不认，会显示成一段乱文本。
而"转成图片贴进去"虽然能看，但公式不能编辑、缩放会糊、在 WPS 里常被当成普通图片错位。

所以按 **MathML → OMML** 手工映射：两者结构几乎一一对应，
这张表覆盖了题库里实际用到的全部命令（`\\overline` `\\dfrac` `\\frac` `\\sqrt` …）
以及常见的下标/上标/求和/积分。

映射关系（MathML 元素 → OMML 元素）
----------------------------------
    math/mrow   →  m:oMath 的内容（顺序拼接，无包装）
    mi / mn / mo/mtext → m:r（m:t 文本）
    mfrac       → m:f（m:num / m:den）
    msqrt       → m:rad（deg 为空 = 平方根）
    mroot       → m:rad（带 m:deg）
    msup        → m:sSup（m:e / m:sup）
    msub        → m:sSub（m:e / m:sub）
    msubsup     → m:sSubSup
    mover(accent)→ m:acc（m:e + m:chr）：\\overline 走这里
    munderover  → m:nary（求和/积分）
    mtable      → m:m（矩阵）
    mstyle/mover(非 accent)/munder → 退化处理（去壳直接接内容）

⚠️ `\\overline` 在 MathML 里是 `<mover accent="true"><mrow>X</mrow><mo>&#x02015;</mo></mover>`，
   OMML 对应的不是 `m:bar` 而是 `m:acc`（重音符）—— Word 里 `m:bar` 是上横线，
   但 `m:acc` 配 U+02015(‾) 才是"X-上划线"的语义，且 WPS 渲染一致。
   实测两者在 WPS/Word 都能显示；这里选 `m:acc` 是因为它对多字符 e 的宽度自适应更好。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List, Optional

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MML_NS = "http://www.w3.org/1998/Math/MathML"

ET.register_namespace("m", M_NS)
ET.register_namespace("w", W_NS)


def _m(tag: str) -> str:
    return f"{{{M_NS}}}{tag}"


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _local(tag: str) -> str:
    """去掉命名空间，只留本地名"""
    return tag.split("}")[-1] if "}" in tag else tag


def _el(tag: str) -> ET.Element:
    return ET.Element(_m(tag))


def _sub(parent: ET.Element, tag: str) -> ET.Element:
    return ET.SubElement(parent, _m(tag))


# ───────────────────────────────────────────── 叶子节点：文本

#: MathML 里的"运算符"字符很多是特殊 Unicode，OMML 里应原样保留，
#: 但要把常见别名归一到更好的字形
_CHAR_FIX = {
    "\u00a0": " ",
}


def _clean_char(s: str) -> str:
    for bad, good in _CHAR_FIX.items():
        s = s.replace(bad, good)
    return s


def _make_run(text: str) -> ET.Element:
    """生成一个 m:r（公式里的文本片段）"""
    r = _el("r")
    t = _sub(r, "t")
    # xml:space="preserve" 保证前后空格不被吃掉（\overline{A} \overline{B} 之间的空格）
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = _clean_char(text)
    return r


def _collect_text(node: ET.Element) -> str:
    """把一个 MathML 子树里的所有文字拼起来（用于未知节点降级）"""
    parts: List[str] = []
    if node.text:
        parts.append(node.text)
    for ch in node:
        parts.append(_collect_text(ch))
        if ch.tail:
            parts.append(ch.tail)
    return "".join(parts)


# ───────────────────────────────────────────── 结构节点

def _wrap(parent: ET.Element, tag: str, children: List[ET.Element], wrap_runs: bool = True) -> ET.Element:
    """
    把一组已转换好的 OMML 片段放进 `<m:tag>` 容器

    wrap_runs=True 时会再套一层 `<m:e>`（OMML 的结构槽位都要求 e/num/den 这种包装），
    但 `m:oMath` 和 `m:r` 不需要。
    """
    holder = _el(tag) if wrap_runs else _el(tag)
    if wrap_runs:
        e = _sub(holder, "e")
        for c in children:
            e.append(c)
    else:
        for c in children:
            holder.append(c)
    return holder


def _attach_implicit_base(items: List[object]) -> List[object]:
    """
    **隐式底数修正**：把「紧邻的正文字符」并入后面的 sSup/sSub

    MathML（以及 latex2mathml 的输出）对 `x^{2}` 会生成**兄弟**节点：

        <mi>x</mi>
        <msup><mi>…空…</mi><mn>2</mn></msup>    ← 或者只有 sup

    而 OMML 的 `<m:sSup>` 要求 `<m:e>` 里放底数。若照搬结构，
    上标就挂在一个空底数上，Word 里会显示成一个孤零零的 "2"（实测就是这样）。
    这里把前一个 run 挪进 `<m:e>`，语义才与 LaTeX 一致。

    只对「前一元素是 m:r 且 sSup/sSub/sSubSup 的 e 为空」的情况生效，
    显式带底数的（`<msup><mi>x</mi><mn>2</mn></msup>`）原样保留。
    """
    out: List[object] = []
    for item in items:
        if isinstance(item, ET.Element) and _local(item.tag) in ("sSup", "sSub", "sSubSup"):
            e = item.find(_m("e"))
            e_is_empty = e is not None and len(e) == 0 and not (e.text or "").strip()
            if e_is_empty and out and isinstance(out[-1], ET.Element) and _local(out[-1].tag) == "r":
                # 取紧邻的一个 run 当底数；若它是多字符（如 `xy`），整段作为底数，
                # 这与 LaTeX 的 `xy^{2}` 语义一致（上标作用于整个前导 token）
                base_run = out.pop()
                if e is not None:
                    e.append(base_run)
        out.append(item)
    return out


def _convert_children(node: ET.Element) -> List[ET.Element]:
    """把一个 MathML 节点的所有子节点逐个转成 OMML 片段"""
    out: List[ET.Element] = []
    for ch in node:
        converted = _convert_node(ch)
        if converted is not None:
            if isinstance(converted, list):
                out.extend(converted)
            else:
                out.append(converted)
    return _attach_implicit_base(out)


def _convert_one_or_many(node: Optional[ET.Element]) -> List[ET.Element]:
    """
    **转换这个节点本身**并按列表返回结果

    ⚠️ 与 `_convert_children` 的区别：这里处理的是**节点自己**，不是它的子节点。
       结构槽位（m:num / m:den / m:e / m:sup …）里放的往往是 `<mi>`、`<mn>`
       这种**叶子**节点 —— 若误用 `_convert_children`，叶子没有子元素，
       就会得到空列表，于是 `<m:e />` 是空的、公式内容凭空消失
       （实测 `x^{2}` 导出后只剩一个孤零零的 "2"）。
    """
    if node is None:
        return []
    converted = _convert_node(node)
    if converted is None:
        return []
    if isinstance(converted, list):
        return converted
    return [converted]


def _convert_node(node: ET.Element) -> Optional[object]:
    """
    MathML 元素 → OMML 片段（可能是单个元素，也可能是列表）

    返回 None 表示"这个元素不产出内容"（例如纯空白 token）。
    """
    name = _local(node.tag)

    # ---- 透明容器：直接展开子节点 ----
    if name in ("math", "mrow", "mstyle", "mpadded", "menclose", "semantics", "mphantom"):
        # semantics 里可能同时有 mathml 和 annotation(LaTeX)，只取第一个子元素
        if name == "semantics":
            kids = _convert_children(node)
            return kids
        return _convert_children(node)

    # ---- 叶子：文本 ----
    if name in ("mi", "mn", "mo", "mtext", "ms"):
        text = _collect_text(node)
        if not text:
            return None
        return _make_run(text)

    # ---- 分数 ----
    if name == "mfrac":
        kids = list(node)
        num = kids[0] if len(kids) > 0 else None
        den = kids[1] if len(kids) > 1 else None
        f = _el("f")
        num_el = _sub(f, "num")
        for c in (_convert_children(num) if num is not None else []):
            num_el.append(c)
        den_el = _sub(f, "den")
        for c in (_convert_children(den) if den is not None else []):
            den_el.append(c)
        return f

    # ---- 根号 ----
    if name == "msqrt":
        rad = _el("rad")
        # 平方根没有次数：deg 留空 + degHide
        deg = _sub(rad, "deg")
        pr = _sub(rad, "radPr")
        hide = ET.SubElement(pr, _m("degHide"))
        hide.set(_m("val"), "1")
        e = _sub(rad, "e")
        for c in _convert_children(node):
            e.append(c)
        return rad

    if name == "mroot":
        kids = list(node)
        rad = _el("rad")
        deg = _sub(rad, "deg")
        if len(kids) > 1:
            for c in _convert_one_or_many(kids[1]):
                deg.append(c)
        e = _sub(rad, "e")
        if len(kids) > 0:
            for c in _convert_one_or_many(kids[0]):
                e.append(c)
        return rad

    # ---- 上标 / 下标 ----
    if name == "msup":
        kids = list(node)
        s = _el("sSup")
        e = _sub(s, "e")
        for c in (_convert_one_or_many(kids[0]) if kids else []):
            e.append(c)
        sup = _sub(s, "sup")
        for c in (_convert_one_or_many(kids[1]) if len(kids) > 1 else []):
            sup.append(c)
        return s

    if name == "msub":
        kids = list(node)
        s = _el("sSub")
        e = _sub(s, "e")
        for c in (_convert_one_or_many(kids[0]) if kids else []):
            e.append(c)
        sub = _sub(s, "sub")
        for c in (_convert_one_or_many(kids[1]) if len(kids) > 1 else []):
            sub.append(c)
        return s

    if name == "msubsup":
        kids = list(node)
        s = _el("sSubSup")
        e = _sub(s, "e")
        for c in (_convert_one_or_many(kids[0]) if kids else []):
            e.append(c)
        sub = _sub(s, "sub")
        for c in (_convert_one_or_many(kids[1]) if len(kids) > 1 else []):
            sub.append(c)
        sup = _sub(s, "sup")
        for c in (_convert_one_or_many(kids[2]) if len(kids) > 2 else []):
            sup.append(c)
        return s

    # ---- 上划线 / 重音 / 下划线 / 下重音 ----
    #   MathML: <mover accent="true"><mrow>X</mrow><mo>‾</mo></mover>
    #   OMML  : <m:acc><m:accPr><m:chr m:val="‾"/></m:accPr><m:e>X</m:e></m:acc>
    if name in ("mover", "munder", "munderover"):
        kids = list(node)
        base = kids[0] if kids else None
        mark = None
        if name == "mover" and len(kids) > 1:
            mark = kids[1]
        elif name == "munder" and len(kids) > 1:
            mark = kids[1]
        elif name == "munderover" and len(kids) > 2:
            mark = kids[1]

        mark_text = _collect_text(mark).strip() if mark is not None else ""
        accent = node.get("accent") or (mark.get("accent") if mark is not None else None)

        # 上划线 / 下划线 / 常见重音 → m:acc（与 Word 的 overline 按钮一致）
        if name == "mover" and mark_text in ("\u203e", "\u00af", "¯", "―", "\u2015", "\u0305", "\u0304", "^", "ˆ"):
            acc = _el("acc")
            pr = _sub(acc, "accPr")
            chr_el = ET.SubElement(pr, _m("chr"))
            # U+0305 = 组合上横线，Word 里显示为最长最标准的"上划线"
            chr_el.set(_m("val"), "\u0305")
            e = _sub(acc, "e")
            for c in (_convert_one_or_many(base) if base is not None else []):
                e.append(c)
            return acc

        if name == "munder" and mark_text in ("\u0332", "\u005f", "_", "\u2015"):
            # 下划线：OMML 用 m:bar pos="bot"
            bar = _el("bar")
            pr = _sub(bar, "barPr")
            pos = ET.SubElement(pr, _m("pos"))
            pos.set(_m("val"), "bot")
            e = _sub(bar, "e")
            for c in (_convert_one_or_many(base) if base is not None else []):
                e.append(c)
            return bar

        # 求和 / 积分这类"上下限"：OMML 用 m:nary
        base_text = _collect_text(base).strip() if base is not None else ""
        if base_text in ("∑", "∏", "∐", "∫", "∬", "∭", "∮", "⋃", "⋂"):
            nary = _el("nary")
            pr = _sub(nary, "naryPr")
            chr_el = ET.SubElement(pr, _m("chr"))
            chr_el.set(_m("val"), base_text)
            lim_loc = ET.SubElement(pr, _m("limLoc"))
            lim_loc.set(_m("val"), "undOvr")
            _sub(nary, "sub")
            _sub(nary, "sup")
            e = _sub(nary, "e")
            # base 本身是符号，不重复输出；这里把被积/求和内容当作 e（MathML 里通常在 mrow 后面）
            return nary

        # 其它上标结构：退化成 sSup/sSub，避免丢内容
        if name == "mover":
            s = _el("sSup")
            e = _sub(s, "e")
            for c in (_convert_one_or_many(base) if base is not None else []):
                e.append(c)
            sup = _sub(s, "sup")
            if mark is not None:
                for c in _convert_one_or_many(mark):
                    sup.append(c)
            return s
        if name == "munder":
            s = _el("sSub")
            e = _sub(s, "e")
            for c in (_convert_one_or_many(base) if base is not None else []):
                e.append(c)
            sub = _sub(s, "sub")
            if mark is not None:
                for c in _convert_one_or_many(mark):
                    sub.append(c)
            return s
        # munderover 兜底：子 + 上标
        s = _el("sSubSup")
        e = _sub(s, "e")
        for c in (_convert_one_or_many(base) if base is not None else []):
            e.append(c)
        _sub(s, "sub")
        _sub(s, "sup")
        return s

    # ---- 表格（矩阵/分段函数）----
    if name == "mtable":
        mat = _el("m")
        for tr in node:
            if _local(tr.tag) != "mtr":
                continue
            mr = _sub(mat, "mr")
            for td in tr:
                if _local(td.tag) != "mtd":
                    continue
                e = _sub(mr, "e")
                for c in _convert_children(td):
                    e.append(c)
        return mat

    if name in ("mtr", "mtd"):
        return _convert_children(node)

    # ---- 未知节点：把文本拼出来，别丢内容 ----
    text = _collect_text(node)
    if text.strip():
        return _make_run(text)
    return None


# ───────────────────────────────────────────── 对外接口

def mathml_to_omml(mathml: str) -> Optional[ET.Element]:
    """
    MathML 字符串 → `<m:oMath>` 元素

    失败返回 None（调用方应降级成纯文本，而不是整篇导出失败）。
    """
    try:
        root = ET.fromstring(mathml)
    except ET.ParseError:
        return None

    # 去掉命名空间前缀便于处理（保留原始 tag 也能工作，_local 已兼容）
    omath = _el("oMath")
    for child in _convert_children(root):
        omath.append(child)
    return omath


def latex_to_omml(latex: str) -> Optional[ET.Element]:
    """LaTeX → `<m:oMath>`；失败返回 None"""
    try:
        import latex2mathml.converter as conv

        mathml = conv.convert(latex)
    except Exception:  # noqa: BLE001
        return None
    return mathml_to_omml(mathml)


def omml_to_xml_string(omath: ET.Element) -> str:
    """把 `<m:oMath>` 序列化成可插入 docx 的 XML 字符串（含 m 命名空间声明）"""
    body = ET.tostring(omath, encoding="unicode")
    # ET 会把命名空间写成 ns0:，统一换成 m:
    body = body.replace("ns0:", "m:").replace(f'xmlns:ns0="{M_NS}"', f'xmlns:m="{M_NS}"')
    if "xmlns:m=" not in body:
        body = body.replace("<m:oMath", f'<m:oMath xmlns:m="{M_NS}"')
    if "xmlns:w=" not in body:
        body = body.replace("<m:oMath", f'<m:oMath xmlns:w="{W_NS}"')
    return body


def omml_plain_text(omath: ET.Element) -> str:
    """把 OMML 元素里的可读文本抽出来（PDF 渲染或降级用）"""
    parts: List[str] = []

    def walk(node: ET.Element):
        local = _local(node.tag)
        if local == "t" and node.text:
            parts.append(node.text)
        for ch in node:
            walk(ch)

    walk(omath)
    return "".join(parts)

